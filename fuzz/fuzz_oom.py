#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: oom - Memory Density (Object Explosion)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Memory Density and Object Explosion Fuzzer (Atheris).

Targets: ftllexengine.syntax.parser.FluentParserV1
Detects "Billion Laughs" style attacks where small inputs generate massive ASTs.

Concern boundary: This fuzzer targets parser-level amplification -- small FTL
inputs that produce disproportionately large AST trees. This is distinct from
the runtime fuzzer (resolver/bundle/cache stack) and currency fuzzer (numeric
parsing). The threat model is denial-of-service via parser object explosion.

Metrics:
- AST node density (nodes per KB of source)
- Real memory usage (RSS via psutil)
- Performance profiling (min/mean/median/p95/p99/max)
- Pathological pattern detection (top 10 densest inputs)
- Seed corpus management (interesting inputs)

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    print("-" * 80, file=sys.stderr)
    print("ERROR: Missing required dependencies for fuzzing:", file=sys.stderr)
    for dep in _MISSING_DEPS:
        print(f"  - {dep}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install with: uv sync --group atheris", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# --- Type Aliases (PEP 695) ---
type FuzzStats = dict[str, int | str | float]
type DensestInput = tuple[float, int, int, str]  # (density, nodes, bytes, source_hash)


# --- Observability State ---
@dataclass
class FuzzerState:
    """Global fuzzer state for observability and metrics."""

    # Core stats
    iterations: int = 0
    findings: int = 0
    status: str = "incomplete"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(default_factory=lambda: deque(maxlen=10000))
    memory_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    # Density tracking
    density_history: deque[float] = field(default_factory=lambda: deque(maxlen=10000))
    densest_inputs: list[DensestInput] = field(default_factory=list)

    # Coverage tracking
    pattern_coverage: dict[str, int] = field(default_factory=dict)

    # Seed corpus
    seed_corpus: dict[str, str] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Corpus productivity
    corpus_entries_added: int = 0

    # Per-pattern wall time (ms)
    pattern_wall_time: dict[str, float] = field(default_factory=dict)

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 1000


# Global state instance
_state = FuzzerState()
_process: psutil.Process | None = None


def _get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


def _build_stats_dict() -> FuzzStats:
    """Build stats dictionary for JSON report."""
    stats: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
    }

    # Performance percentiles
    if _state.performance_history:
        perf_data = list(_state.performance_history)
        n = len(perf_data)
        stats["perf_mean_ms"] = round(statistics.mean(perf_data), 3)
        stats["perf_median_ms"] = round(statistics.median(perf_data), 3)
        stats["perf_min_ms"] = round(min(perf_data), 3)
        stats["perf_max_ms"] = round(max(perf_data), 3)
        if n >= 20:
            quantiles = statistics.quantiles(perf_data, n=20)
            stats["perf_p95_ms"] = round(quantiles[18], 3)
        if n >= 100:
            quantiles = statistics.quantiles(perf_data, n=100)
            stats["perf_p99_ms"] = round(quantiles[98], 3)

    # Memory tracking
    if _state.memory_history:
        mem_data = list(_state.memory_history)
        stats["memory_mean_mb"] = round(statistics.mean(mem_data), 2)
        stats["memory_peak_mb"] = round(max(mem_data), 2)
        stats["memory_delta_mb"] = round(max(mem_data) - _state.initial_memory_mb, 2)

        # Memory leak detection (quarter comparison for accuracy)
        if len(mem_data) >= 40:
            first_quarter = mem_data[: len(mem_data) // 4]
            last_quarter = mem_data[-(len(mem_data) // 4) :]
            first_avg = statistics.mean(first_quarter)
            last_avg = statistics.mean(last_quarter)
            growth_mb = last_avg - first_avg
            stats["memory_leak_detected"] = 1 if growth_mb > 10.0 else 0
            stats["memory_growth_mb"] = round(growth_mb, 2)
        else:
            stats["memory_leak_detected"] = 0

    # Density distribution
    if _state.density_history:
        density_data = list(_state.density_history)
        stats["density_mean"] = round(statistics.mean(density_data), 1)
        stats["density_median"] = round(statistics.median(density_data), 1)
        stats["density_max"] = round(max(density_data), 1)

    # Pattern coverage
    stats["patterns_tested"] = len(_state.pattern_coverage)
    for pattern, count in sorted(_state.pattern_coverage.items()):
        stats[f"pattern_{pattern}"] = count

    # Corpus and density tracking
    stats["seed_corpus_size"] = len(_state.seed_corpus)
    stats["corpus_entries_added"] = _state.corpus_entries_added
    stats["densest_inputs_tracked"] = len(_state.densest_inputs)

    # Per-pattern wall time
    for pattern, total_ms in sorted(_state.pattern_wall_time.items()):
        stats[f"wall_time_ms_{pattern}"] = round(total_ms, 1)

    return stats


def _emit_final_report() -> None:
    """Emit comprehensive final report (crash-proof, writes to stderr and file)."""
    _state.status = "complete"
    stats = _build_stats_dict()
    report = json.dumps(stats, sort_keys=True)

    # Emit to stderr for capture
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr, flush=True)

    # Write to file for shell script parsing (best-effort)
    try:
        report_file = pathlib.Path(".fuzz_corpus") / "oom" / "fuzz_oom_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass  # Best-effort file write


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.syntax.parser import FluentParserV1


def count_nodes(node: Any) -> int:
    """Count AST nodes via recursive attribute traversal.

    Uses attribute probing to handle all AST node types without importing
    the full AST module (which would add coupling to node class internals).
    """
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


# --- Pathological Pattern Constants ---
_IDENTIFIERS: Sequence[str] = (
    "msg", "msg2", "msg3", "a", "b", "c", "d", "e",
)

_VAR_NAMES: Sequence[str] = (
    "$var", "$sel", "$count", "$type", "$x",
)

_SELECTOR_KEYS: Sequence[str] = (
    "one", "two", "few", "many", "other", "zero",
)


def _generate_pathological_ftl(  # noqa: PLR0911, PLR0912, PLR0915
    fdp: atheris.FuzzedDataProvider,
) -> tuple[str, str]:
    """Generate pathological FTL patterns targeting AST explosion.

    16 pattern types targeting distinct amplification vectors.
    High branch count maps fuzzed bytes to structurally diverse attack patterns.

    Returns:
        (pattern_name, ftl_source)
    """
    weights = [8, 8, 7, 7, 8, 7, 7, 7, 10, 6, 6, 6, 6, 6, 6, 5]  # 16 patterns
    total_weight = sum(weights)
    choice = fdp.ConsumeIntInRange(0, total_weight - 1)

    cumulative = 0
    pattern_choice = 0
    for i, weight in enumerate(weights):
        cumulative += weight
        if choice < cumulative:
            pattern_choice = i
            break

    depth = fdp.ConsumeIntInRange(1, 200)
    msg_id = "msg"

    match pattern_choice:
        case 0:  # Placeable nesting
            source = f"{msg_id} = " + ("{ " * depth) + "$var" + (" }" * depth) + "\n"
            return ("placeable_nest", source)

        case 1:  # Attribute explosion
            attrs = "\n".join(f"    .attr{i} = val" for i in range(depth))
            source = f"{msg_id} = val\n{attrs}\n"
            return ("attribute_explosion", source)

        case 2:  # Select nesting
            nested = "$type"
            for i in range(depth):
                nested = f"{{ {nested} ->\n    [opt{i}] Inner\n   *[other] Outer\n}}"
            source = f"{msg_id} = {nested}\n"
            return ("select_nest", source)

        case 3:  # Variant explosion
            variants = "\n".join(f"    [var{i}] Value {i}" for i in range(depth))
            source = f"{msg_id} = {{ $sel ->\n{variants}\n   *[other] Default\n}}\n"
            return ("variant_explosion", source)

        case 4:  # Reference chain
            refs = "\n".join(f"msg{i} = {{ msg{i + 1} }}" for i in range(depth))
            source = f"{refs}\nmsg{depth} = Final\n"
            return ("reference_chain", source)

        case 5:  # Term nesting
            terms = "\n".join(f"-term{i} = {{ -term{i + 1} }}" for i in range(depth))
            source = f"{terms}\n-term{depth} = Base\n{msg_id} = {{ -term0 }}\n"
            return ("term_nest", source)

        case 6:  # Mixed placeables and selects
            mixed = "{ " * (depth // 2) + "$var" + " }" * (depth // 2)
            source = f"{msg_id} = {{ $sel ->\n    [a] {mixed}\n   *[b] Other\n}}\n"
            return ("mixed_placeable_select", source)

        case 7:  # Attribute + Select combination
            attrs = "\n".join(
                f"    .attr{i} = {{ $sel ->\n        [a] Val\n       *[b] Other\n    }}"
                for i in range(min(depth, 50))
            )
            source = f"{msg_id} = Root\n{attrs}\n"
            return ("attribute_select_combo", source)

        case 8:  # Raw bytes pass-through (let libFuzzer mutations drive)
            raw = fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, 500))
            return ("raw_bytes", raw)

        case 9:  # Comment flooding (parser must skip N comments)
            comments = "\n".join(f"# Comment line {i}" for i in range(depth))
            source = f"{comments}\n{msg_id} = value\n"
            return ("comment_flood", source)

        case 10:  # Message flooding (many small messages)
            messages = "\n".join(f"m{i} = value{i}" for i in range(depth))
            return ("message_flood", messages + "\n")

        case 11:  # Multiline value with continuations
            lines = "\n    ".join(f"line {i}" for i in range(depth))
            source = f"{msg_id} =\n    {lines}\n"
            return ("multiline_value", source)

        case 12:  # Variant with expressions in each arm
            var = fdp.PickValueInList(list(_VAR_NAMES))
            variants_parts: list[str] = []
            for i in range(min(depth, 100)):
                # Each variant arm has a placeable
                prefix = "*" if i == 0 else ""
                variants_parts.append(
                    f"    [{prefix}v{i}] {{ {var} }} text {i}"
                )
            variants_str = "\n".join(variants_parts)
            source = f"{msg_id} = {{ $sel ->\n{variants_str}\n}}\n"
            return ("variant_expression_explosion", source)

        case 13:  # Cyclic references (self-referencing messages)
            chain_len = min(depth, 50)
            parts: list[str] = []
            for i in range(chain_len):
                next_id = f"c{(i + 1) % chain_len}"
                parts.append(f"c{i} = {{ {next_id} }}")
            source = "\n".join(parts) + "\n"
            return ("cyclic_chain", source)

        case 14:  # Mixed terms and messages with cross-references
            terms = "\n".join(f"-t{i} = Term{i}" for i in range(min(depth, 50)))
            msgs = "\n".join(
                f"m{i} = {{ -t{i % min(depth, 50)} }}" for i in range(min(depth, 50))
            )
            source = f"{terms}\n{msgs}\n"
            return ("term_message_cross_ref", source)

        case 15:  # Attributes with deep placeable nesting
            nest_depth = min(depth, 30)
            inner = "$var"
            for _ in range(nest_depth):
                inner = f"{{ {inner} }}"
            num_attrs = fdp.ConsumeIntInRange(1, 20)
            attrs_list = "\n".join(f"    .a{i} = {inner}" for i in range(num_attrs))
            source = f"{msg_id} = root\n{attrs_list}\n"
            return ("attr_deep_placeable", source)

        case _:
            # Unreachable fallback
            return ("fallback", f"{msg_id} = Fallback\n")


def _track_densest_input(
    density: float,
    node_count: int,
    source_bytes: int,
    source: str,
) -> None:
    """Track top 10 densest inputs using min-heap."""
    source_hash = hashlib.sha256(
        source.encode("utf-8", errors="surrogatepass")
    ).hexdigest()[:16]
    entry: DensestInput = (density, node_count, source_bytes, source_hash)

    if len(_state.densest_inputs) < 10:
        heapq.heappush(_state.densest_inputs, entry)
    elif density > _state.densest_inputs[0][0]:  # Beat minimum
        heapq.heapreplace(_state.densest_inputs, entry)


def _track_seed_corpus(source: str, pattern: str, density: float) -> None:
    """Track interesting inputs for seed corpus with LRU-like eviction."""
    is_interesting = density > 1000 or "raw_bytes" in pattern or "cyclic" in pattern

    if is_interesting:
        source_hash = hashlib.sha256(
            source.encode("utf-8", errors="surrogatepass")
        ).hexdigest()[:16]
        if source_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[source_hash] = source
            _state.corpus_entries_added += 1


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Detect billion laughs style AST explosion attacks.

    Observability:
    - Performance: Tracks timing per iteration
    - Memory: Tracks RSS via psutil
    - Density: Tracks AST nodes per KB (threshold: 5000 nodes/KB)
    - Patterns: Coverage of 16 pathological pattern types
    - Corpus: Interesting inputs (density > 1000, raw bytes, cyclic)
    """
    # Initialize memory baseline on first iteration
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic report write for shell script parsing
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    # Performance timing
    start_time = time.perf_counter()

    fdp = atheris.FuzzedDataProvider(data)

    # Generate pathological FTL (16 pattern types with weighted selection)
    pattern_name, source = _generate_pathological_ftl(fdp)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    parser = FluentParserV1(max_source_size=1024 * 1024, max_nesting_depth=500)

    try:
        res = parser.parse(source)
        node_count = count_nodes(res)

        # Density check: Nodes per KB of source
        source_bytes = len(source.encode("utf-8", errors="surrogatepass"))
        source_size_kb = max(source_bytes / 1024.0, 0.1)
        density = node_count / source_size_kb

        # Track metrics
        _state.density_history.append(density)
        _track_densest_input(density, node_count, source_bytes, source)
        _track_seed_corpus(source, pattern_name, density)

        # Threshold: 5000 nodes/KB is pathological for Fluent 1.0 spec
        # Record as finding but do NOT raise -- crashing the fuzzer prevents
        # further exploration and causes libFuzzer to treat it as a bug
        if density > 5000:
            _state.findings += 1

    except (ValueError, RecursionError, MemoryError, FrozenFluentError):
        # Expected: Parser enforces max_nesting_depth and max_source_size.
        # FrozenFluentError: depth guard fires MAX_DEPTH_EXCEEDED as a safety
        # mechanism regardless of strict mode to prevent stack overflow.
        pass
    except Exception:
        # Unexpected exceptions are findings -- re-raise for Atheris to capture
        _state.findings += 1
        raise
    finally:
        # Performance tracking
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)

        # Per-pattern wall time accumulation
        _state.pattern_wall_time[pattern_name] = (
            _state.pattern_wall_time.get(pattern_name, 0.0) + elapsed_ms
        )

        # Memory tracking (every 100 iterations to reduce overhead)
        if _state.iterations % 100 == 0:
            current_memory_mb = _get_process().memory_info().rss / (1024 * 1024)
            _state.memory_history.append(current_memory_mb)


def main() -> None:
    """Run the OOM fuzzer with optional --help."""
    parser = argparse.ArgumentParser(
        description="Memory density / object explosion fuzzer using Atheris/libFuzzer",
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size",
        type=int,
        default=1000,
        help="Maximum size of in-memory seed corpus (default: 1000)",
    )

    # Parse known args, pass rest to Atheris/libFuzzer
    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    # Reconstruct sys.argv for Atheris
    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Memory Density / Object Explosion Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     ftllexengine.syntax.parser.FluentParserV1")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Threshold:  5000 nodes/KB (pathological density)")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
