#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: oom - Memory Density (Object Explosion)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Memory Density & Object Explosion Fuzzer (Atheris).

Targets: ftllexengine.syntax.parser.FluentParserV1
Detects "Billion Laughs" style attacks where small inputs generate massive ASTs.

Metrics:
- AST node density (nodes per KB of source)
- Real memory usage (RSS via psutil)
- Performance profiling (min/mean/median/p95/p99/max)
- Pathological pattern detection (top 10 densest inputs)
- Seed corpus management (interesting inputs)
"""

from __future__ import annotations

import atexit
import hashlib
import heapq
import json
import logging
import os
import statistics
import sys
import time
from collections import deque
from typing import Any

try:
    import psutil
except ImportError:
    print("[ERROR] psutil not found. Install: uv pip install psutil", file=sys.stderr)
    sys.exit(1)

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float]
type DensestInput = tuple[float, int, int, str]  # (density, nodes, bytes, source_hash)

# --- Global Observability State ---
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}
performance_history: deque[float] = deque(maxlen=1000)
memory_history: deque[float] = deque(maxlen=100)
density_history: deque[float] = deque(maxlen=1000)
densest_inputs: list[DensestInput] = []  # Min-heap (top 10 pathological)
pattern_coverage: dict[str, int] = {}
seed_corpus: dict[str, str] = {}  # hash -> source (interesting inputs)
_process: psutil.Process = psutil.Process(os.getpid())
_initial_memory_mb: float = 0.0

def _emit_final_report() -> None:
    """Emit comprehensive final report matching fuzz_cache.py pattern."""
    # Performance percentiles
    if performance_history:
        perf_data = list(performance_history)
        _fuzz_stats["perf_mean_ms"] = round(statistics.mean(perf_data), 3)
        _fuzz_stats["perf_median_ms"] = round(statistics.median(perf_data), 3)
        _fuzz_stats["perf_p95_ms"] = round(
            statistics.quantiles(perf_data, n=20)[18], 3
        ) if len(perf_data) >= 20 else 0.0
        _fuzz_stats["perf_p99_ms"] = round(
            statistics.quantiles(perf_data, n=100)[98], 3
        ) if len(perf_data) >= 100 else 0.0
        _fuzz_stats["perf_min_ms"] = round(min(perf_data), 3)
        _fuzz_stats["perf_max_ms"] = round(max(perf_data), 3)

    # Memory tracking
    if memory_history:
        mem_data = list(memory_history)
        _fuzz_stats["memory_mean_mb"] = round(statistics.mean(mem_data), 2)
        _fuzz_stats["memory_peak_mb"] = round(max(mem_data), 2)
        _fuzz_stats["memory_delta_mb"] = round(
            max(mem_data) - _initial_memory_mb, 2
        )

    # Density distribution
    if density_history:
        density_data = list(density_history)
        _fuzz_stats["density_mean"] = round(statistics.mean(density_data), 1)
        _fuzz_stats["density_median"] = round(statistics.median(density_data), 1)
        _fuzz_stats["density_max"] = round(max(density_data), 1)

    # Pattern coverage
    _fuzz_stats["patterns_tested"] = len(pattern_coverage)
    for pattern, count in sorted(pattern_coverage.items()):
        _fuzz_stats[f"pattern_{pattern}"] = count

    # Seed corpus
    _fuzz_stats["seed_corpus_size"] = len(seed_corpus)

    # Top 10 densest inputs (pathological patterns)
    _fuzz_stats["densest_inputs_tracked"] = len(densest_inputs)

    # Memory leak detection (similar to fuzz_cache.py)
    if len(memory_history) >= 10:
        mem_data = list(memory_history)
        first_10_avg = statistics.mean(mem_data[:10])
        last_10_avg = statistics.mean(mem_data[-10:])
        growth_mb = last_10_avg - first_10_avg
        if growth_mb > 5.0:  # >5MB growth indicates potential leak
            _fuzz_stats["memory_leak_detected"] = 1
            _fuzz_stats["memory_growth_mb"] = round(growth_mb, 2)
        else:
            _fuzz_stats["memory_leak_detected"] = 0

    _fuzz_stats["status"] = "complete"

    report = json.dumps(_fuzz_stats, sort_keys=True)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)

atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    sys.exit(1)

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.parser import FluentParserV1

class MemoryDensityError(Exception):
    """Raised when AST object density exceeds safe limits."""

def count_nodes(node: Any) -> int:
    """Recursively count AST nodes with optimized traversal."""
    count = 1
    if hasattr(node, "entries"):  # Resource
        for entry in node.entries:
            count += count_nodes(entry)
    if hasattr(node, "value") and node.value:  # Message/Term/Attribute
        count += count_nodes(node.value)
    if hasattr(node, "attributes"):  # Message/Term
        for attr in node.attributes:
            count += count_nodes(attr)
    if hasattr(node, "elements"):  # Pattern
        for elem in node.elements:
            count += count_nodes(elem)
    if hasattr(node, "expression"):  # Placeable
        count += count_nodes(node.expression)
    if hasattr(node, "selector"):  # SelectExpression
        count += count_nodes(node.selector)
    if hasattr(node, "variants"):  # SelectExpression
        for variant in node.variants:
            count += count_nodes(variant)
    return count

def _generate_pathological_ftl(  # noqa: PLR0911 - Each case returns specific pattern
    fdp: atheris.FuzzedDataProvider,
) -> tuple[str, str]:
    """Generate pathological FTL patterns targeting AST explosion.

    Returns:
        (pattern_name, ftl_source)
    """
    pattern_choice = fdp.ConsumeIntInRange(0, 7)
    depth = fdp.ConsumeIntInRange(1, 200)
    msg_id = "msg"

    match pattern_choice:
        case 0:  # Placeable nesting
            source = f"{msg_id} = " + ("{" * depth) + " $var " + ("}" * depth) + "\n"
            return ("placeable_nest", source)

        case 1:  # Attribute explosion
            attrs = "\n".join([f"    .attr{i} = val" for i in range(depth)])
            source = f"{msg_id} = val\n{attrs}\n"
            return ("attribute_explosion", source)

        case 2:  # Select nesting
            selector = "$type"
            nested = selector
            for i in range(depth):
                nested = f"{{ {nested} ->\n    [opt{i}] Inner\n   *[other] Outer\n}}"
            source = f"{msg_id} = {nested}\n"
            return ("select_nest", source)

        case 3:  # Variant explosion
            variants = "\n".join([f"    [var{i}] Value {i}" for i in range(depth)])
            source = f"{msg_id} = {{ $sel ->\n{variants}\n   *[other] Default\n}}\n"
            return ("variant_explosion", source)

        case 4:  # Reference chain
            refs = "\n".join([f"msg{i} = {{ msg{i+1} }}" for i in range(depth)])
            source = f"{refs}\nmsg{depth} = Final\n"
            return ("reference_chain", source)

        case 5:  # Term nesting
            terms = "\n".join([f"-term{i} = {{ -term{i+1} }}" for i in range(depth)])
            source = f"{terms}\n-term{depth} = Base\n{msg_id} = {{ -term0 }}\n"
            return ("term_nest", source)

        case 6:  # Mixed placeables and selects
            mixed = "{" * (depth // 2) + " $var " + ("}" * (depth // 2))
            source = f"{msg_id} = {{ $sel ->\n    [a] {mixed}\n   *[b] Other\n}}\n"
            return ("mixed_placeable_select", source)

        case 7:  # Attribute + Select combination
            attrs = "\n".join([
                f"    .attr{i} = {{ $sel ->\n        [a] Val\n       *[b] Other\n    }}"
                for i in range(min(depth, 50))
            ])
            source = f"{msg_id} = Root\n{attrs}\n"
            return ("attribute_select_combo", source)

        case _:
            # Fallback (unreachable with ConsumeIntInRange(0, 7))
            source = f"{msg_id} = Fallback\n"
            return ("fallback", source)

def _track_densest_input(
    density: float,
    node_count: int,
    source_bytes: int,
    source: str,
) -> None:
    """Track top 10 densest inputs using min-heap."""
    source_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
    entry: DensestInput = (density, node_count, source_bytes, source_hash)

    if len(densest_inputs) < 10:
        heapq.heappush(densest_inputs, entry)
    elif density > densest_inputs[0][0]:  # Beat minimum
        heapq.heapreplace(densest_inputs, entry)

def _track_seed_corpus(source: str, density: float) -> None:
    """Track interesting inputs for seed corpus (density > 1000)."""
    # Independent conditions: density threshold and corpus size limit
    if density > 1000 and len(seed_corpus) < 1000:  # pylint: disable=chained-comparison
        source_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
        if source_hash not in seed_corpus:
            seed_corpus[source_hash] = source

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Detect billion laughs style AST explosion attacks.

    Observability:
    - Performance: Tracks timing per iteration
    - Memory: Tracks RSS via psutil
    - Density: Tracks AST nodes per KB
    - Patterns: Coverage of pathological patterns
    - Corpus: Interesting inputs (density > 1000)
    """
    # Fuzzing observability pattern: global state for memory baseline tracking
    global _initial_memory_mb  # noqa: PLW0603  # pylint: disable=global-statement

    # Initialize memory baseline on first iteration
    if _fuzz_stats["iterations"] == 0:
        _initial_memory_mb = _process.memory_info().rss / (1024 * 1024)

    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    # Performance timing
    start_time = time.perf_counter()

    fdp = atheris.FuzzedDataProvider(data)

    # Generate pathological FTL (8 pattern types)
    pattern_name, source = _generate_pathological_ftl(fdp)
    pattern_coverage[pattern_name] = pattern_coverage.get(pattern_name, 0) + 1

    parser = FluentParserV1(max_source_size=1024 * 1024, max_nesting_depth=500)

    try:
        res = parser.parse(source)
        node_count = count_nodes(res)

        # Density check: Nodes per KB of source
        source_bytes = len(source)
        source_size_kb = max(source_bytes / 1024.0, 0.1)
        density = node_count / source_size_kb

        # Track metrics
        density_history.append(density)
        _track_densest_input(density, node_count, source_bytes, source)
        _track_seed_corpus(source, density)

        # Memory tracking (every 100 iterations to reduce overhead)
        if _fuzz_stats["iterations"] % 100 == 0:
            current_memory_mb = _process.memory_info().rss / (1024 * 1024)
            memory_history.append(current_memory_mb)

        # Threshold: 5000 nodes/KB is pathological for Fluent 1.0 spec
        if density > 5000:
            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            msg = (
                f"Pathological density: {density:.1f} nodes/KB "
                f"({node_count} nodes for {source_bytes} bytes, pattern={pattern_name})"
            )
            raise MemoryDensityError(msg)

    except (ValueError, RecursionError, MemoryError):
        # Expected: Parser enforces max_nesting_depth and max_source_size
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise
    finally:
        # Performance tracking
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        performance_history.append(elapsed_ms)

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
