"""Shared fuzzing infrastructure for Atheris-based fuzzers.

Provides common observability, metrics, seed corpus management, and reporting
used by all fuzz targets. Each fuzzer imports from this module and composes
domain-specific state alongside BaseFuzzerState.

Not a fuzz target itself -- no FUZZ_PLUGIN header, not discoverable by
fuzz_atheris.sh.
"""

from __future__ import annotations

import hashlib
import heapq
import json
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

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]


# --- PEP 695 Type Aliases ---

type FuzzStats = dict[str, int | str | float | list[Any]]
type InterestingInput = tuple[float, str, str]  # (neg_duration_ms, pattern, input_hash)

# --- Constants ---

GC_INTERVAL = 256
"""Periodic gc.collect() interval to reclaim Atheris instrumentation cycles."""


# --- Process Handle (lazy singleton) ---

_process: psutil.Process | None = None


def get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


# --- Dependency Checks ---


def check_dependencies(dep_names: Sequence[str], dep_modules: Sequence[Any]) -> None:
    """Verify fuzzing dependencies are importable, exit with instructions if not.

    Args:
        dep_names: Human-readable names (e.g., ["psutil", "atheris"])
        dep_modules: Corresponding module objects (None if import failed)
    """
    missing = [name for name, mod in zip(dep_names, dep_modules, strict=True) if mod is None]
    if missing:
        print("-" * 80, file=sys.stderr)
        print("ERROR: Missing required dependencies for fuzzing:", file=sys.stderr)
        for dep in missing:
            print(f"  - {dep}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install with: uv sync --group atheris", file=sys.stderr)
        print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
        print("-" * 80, file=sys.stderr)
        sys.exit(1)


# --- Base Fuzzer State ---


@dataclass
class BaseFuzzerState:
    """Common observability state shared by all fuzzers.

    Domain-specific fuzzers maintain separate dataclasses for their
    custom metrics and compose them alongside this base state.
    """

    # Core stats
    iterations: int = 0
    findings: int = 0
    status: str = "incomplete"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=10000),
    )
    memory_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=1000),
    )

    # Pattern coverage
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Interesting inputs (max-heap for slowest, in-memory corpus)
    slowest_operations: list[InterestingInput] = field(default_factory=list)
    seed_corpus: dict[str, bytes] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Corpus productivity
    corpus_entries_added: int = 0
    corpus_evictions: int = 0

    # Finding artifact counter
    finding_counter: int = 0

    # Per-pattern wall time (ms)
    pattern_wall_time: dict[str, float] = field(default_factory=dict)

    # Weight distribution tracking (intended weights for skew detection)
    pattern_intended_weights: dict[str, float] = field(default_factory=dict)

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 500


# --- Weighted Schedule ---


def build_weighted_schedule(
    items: Sequence[str],
    weights: Sequence[int],
) -> tuple[str, ...]:
    """Pre-compute a weighted schedule from items.

    Returns a tuple of length sum(weights) where each item appears
    proportional to its weight. Used by FDP-based pattern routing
    so that crash files are self-contained and replayable.
    """
    schedule: list[str] = []
    for item, weight in zip(items, weights, strict=True):
        schedule.extend([item] * weight)
    return tuple(schedule)


# --- Slowest Operation Tracking ---


def track_slowest_operation(
    state: BaseFuzzerState,
    duration_ms: float,
    pattern: str,
    input_hash: str,
) -> None:
    """Track top 10 slowest operations using max-heap.

    Args:
        state: Fuzzer state to update
        duration_ms: Operation duration in milliseconds
        pattern: Pattern name that produced this operation
        input_hash: Truncated SHA-256 hex digest of input
    """
    entry: InterestingInput = (-duration_ms, pattern, input_hash)
    if len(state.slowest_operations) < 10:
        heapq.heappush(state.slowest_operations, entry)
    elif -duration_ms < state.slowest_operations[0][0]:
        heapq.heapreplace(state.slowest_operations, entry)


# --- Seed Corpus Management ---


def track_seed_corpus(
    state: BaseFuzzerState,
    input_key: str,
    input_data: bytes,
    *,
    is_interesting: bool,
) -> None:
    """Track interesting inputs with FIFO eviction.

    Tracks corpus_evictions when the corpus is full and an entry is evicted,
    enabling corpus retention rate computation in reporting.

    Args:
        state: Fuzzer state to update
        input_key: Hash key for deduplication
        input_data: Raw input bytes to store
        is_interesting: Whether this input qualifies for corpus inclusion
    """
    if not is_interesting:
        return

    if input_key in state.seed_corpus:
        return

    if len(state.seed_corpus) >= state.seed_corpus_max_size:
        oldest_key = next(iter(state.seed_corpus))
        del state.seed_corpus[oldest_key]
        state.corpus_evictions += 1

    state.seed_corpus[input_key] = input_data
    state.corpus_entries_added += 1


# --- Input Hashing ---


def hash_input(data: bytes) -> str:
    """Compute truncated SHA-256 hex digest for corpus deduplication."""
    return hashlib.sha256(data).hexdigest()[:16]


# --- Performance / Memory Tracking ---


def record_iteration_metrics(
    state: BaseFuzzerState,
    pattern: str,
    start_time: float,
    input_data: bytes,
    *,
    is_interesting: bool,
) -> None:
    """Record per-iteration performance and corpus metrics.

    Call in the finally block of test_one_input.

    Args:
        state: Fuzzer state to update
        pattern: Pattern name for this iteration
        start_time: time.perf_counter() value from iteration start
        input_data: Raw input bytes for corpus and slowest tracking
        is_interesting: Whether input qualifies for seed corpus
    """
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    state.performance_history.append(elapsed_ms)
    state.pattern_wall_time[pattern] = state.pattern_wall_time.get(pattern, 0.0) + elapsed_ms

    input_hash = hash_input(input_data)
    track_slowest_operation(state, elapsed_ms, pattern, input_hash)
    track_seed_corpus(state, input_hash, input_data, is_interesting=is_interesting)


def record_memory(state: BaseFuzzerState) -> None:
    """Sample current RSS memory usage (call every ~100 iterations)."""
    current_mb = get_process().memory_info().rss / (1024 * 1024)
    state.memory_history.append(current_mb)


# --- Stats Building ---


def build_base_stats_dict(
    state: BaseFuzzerState,
    *,
    coverage_key: str = "patterns_tested",
    coverage_prefix: str = "pattern_",
    wall_time_prefix: str = "wall_time_ms_",
) -> FuzzStats:
    """Build common stats dictionary for JSON report.

    Includes weight skew detection and corpus retention metrics.

    Args:
        state: Fuzzer state to report on
        coverage_key: JSON key for pattern/scenario count
        coverage_prefix: Prefix for per-pattern/scenario count keys
        wall_time_prefix: Prefix for per-pattern/scenario wall time keys

    Returns:
        Stats dictionary suitable for JSON serialization
    """
    stats: FuzzStats = {
        "status": state.status,
        "iterations": state.iterations,
        "findings": state.findings,
    }

    # Performance percentiles
    if state.performance_history:
        perf_data = list(state.performance_history)
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
    if state.memory_history:
        mem_data = list(state.memory_history)
        stats["memory_mean_mb"] = round(statistics.mean(mem_data), 2)
        stats["memory_peak_mb"] = round(max(mem_data), 2)
        stats["memory_delta_mb"] = round(max(mem_data) - state.initial_memory_mb, 2)

        if len(mem_data) >= 40:
            first_quarter = mem_data[: len(mem_data) // 4]
            last_quarter = mem_data[-(len(mem_data) // 4) :]
            growth_mb = statistics.mean(last_quarter) - statistics.mean(first_quarter)
            stats["memory_leak_detected"] = 1 if growth_mb > 10.0 else 0
            stats["memory_growth_mb"] = round(growth_mb, 2)
        else:
            stats["memory_leak_detected"] = 0
            stats["memory_growth_mb"] = 0.0

    # Pattern/scenario coverage
    stats[coverage_key] = len(state.pattern_coverage)
    for pattern, count in sorted(state.pattern_coverage.items()):
        stats[f"{coverage_prefix}{pattern}"] = count

    # Error distribution
    stats["error_types"] = len(state.error_counts)
    for error_type, count in sorted(state.error_counts.items()):
        clean_key = error_type[:50].replace("<", "").replace(">", "")
        stats[f"error_{clean_key}"] = count

    # Corpus stats with retention metrics
    stats["seed_corpus_size"] = len(state.seed_corpus)
    stats["corpus_entries_added"] = state.corpus_entries_added
    stats["corpus_evictions"] = state.corpus_evictions
    stats["corpus_retention_rate"] = round(
        len(state.seed_corpus) / max(1, state.corpus_entries_added),
        4,
    )
    stats["slowest_operations_tracked"] = len(state.slowest_operations)

    # Per-pattern/scenario wall time
    for pattern, total_ms in sorted(state.pattern_wall_time.items()):
        stats[f"{wall_time_prefix}{pattern}"] = round(total_ms, 1)

    # Weight skew detection
    _add_weight_skew_stats(state, stats)

    return stats


def _add_weight_skew_stats(state: BaseFuzzerState, stats: FuzzStats) -> None:
    """Detect and report weight distribution skew.

    LibFuzzer's coverage-guided feedback can override the weighted schedule,
    causing actual pattern distribution to diverge significantly from intended.
    Reports which patterns deviate by more than 3x from their intended weight.
    """
    if not state.pattern_intended_weights or state.iterations < 1000:
        stats["weight_skew_detected"] = 0
        return

    total_weight = sum(state.pattern_intended_weights.values())
    if total_weight == 0:
        stats["weight_skew_detected"] = 0
        return

    total_iters = state.iterations
    skewed: list[str] = []

    for pattern, intended_weight in state.pattern_intended_weights.items():
        intended_pct = (intended_weight / total_weight) * 100
        actual_count = state.pattern_coverage.get(pattern, 0)
        actual_pct = (actual_count / total_iters) * 100

        stats[f"weight_actual_pct_{pattern}"] = round(actual_pct, 2)
        stats[f"weight_intended_pct_{pattern}"] = round(intended_pct, 2)

        if intended_pct > 0:
            ratio = actual_pct / intended_pct
            if ratio > 3.0 or ratio < 0.33:
                skewed.append(pattern)

    stats["weight_skew_detected"] = 1 if skewed else 0
    stats["weight_skew_patterns"] = skewed


# --- Reporting ---


def emit_final_report(
    state: BaseFuzzerState,
    stats: FuzzStats,
    report_dir: pathlib.Path,
    report_filename: str,
) -> None:
    """Emit crash-proof JSON report to stderr and file.

    Args:
        state: Fuzzer state (status set to "complete")
        stats: Pre-built stats dictionary
        report_dir: Directory for the JSON report file
        report_filename: Filename for the JSON report
    """
    state.status = "complete"
    report = json.dumps(stats, sort_keys=True)

    print(
        f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]",
        file=sys.stderr,
        flush=True,
    )

    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / report_filename).write_text(report, encoding="utf-8")
    except OSError:
        pass
