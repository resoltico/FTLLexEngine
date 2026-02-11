"""Shared fuzzing infrastructure for Atheris-based fuzzers.

Provides common observability, metrics, seed corpus management, and reporting
used by all fuzz targets. Each fuzzer imports from this module and composes
domain-specific state alongside BaseFuzzerState.

Not a fuzz target itself -- no FUZZ_PLUGIN header, not discoverable by
fuzz_atheris.sh.
"""

from __future__ import annotations

import datetime
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
type PerformanceOutlier = tuple[float, str, str, str]  # (duration_ms, pattern, hash, timestamp)

# --- Constants ---

GC_INTERVAL = 256
"""Periodic gc.collect() interval to reclaim Atheris instrumentation cycles."""

# Adaptive time budget: abort pattern if exceeds this multiplier of mean cost
TIME_BUDGET_MULTIPLIER = 10.0
"""Maximum allowed time for a pattern relative to its historical mean."""

# Performance outlier threshold: track inputs exceeding P99 by this factor
OUTLIER_THRESHOLD_FACTOR = 2.0
"""Track inputs exceeding P99 latency by this factor."""


# --- Process Handle (lazy singleton) ---

_process: psutil.Process | None = None
_process_pid: int = 0


def get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle.

    Detects PID mismatch after fork() and re-initializes to avoid
    monitoring the parent process from a child worker.
    """
    global _process, _process_pid  # noqa: PLW0603  # pylint: disable=global-statement
    current_pid = os.getpid()
    if _process is None or _process_pid != current_pid:
        _process = psutil.Process(current_pid)
        _process_pid = current_pid
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

    # Fuzzer identification (for self-describing JSON reports)
    fuzzer_name: str = ""
    fuzzer_target: str = ""

    # Core stats
    iterations: int = 0
    findings: int = 0
    status: str = "incomplete"

    # Campaign timing
    campaign_start_time: float = 0.0

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

    # Pattern-stratified corpus buckets (pattern -> {hash -> data})
    corpus_pattern_buckets: dict[str, dict[str, bytes]] = field(default_factory=dict)

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 500

    # Adaptive time budgets (pattern -> mean cost in ms)
    pattern_mean_cost: dict[str, float] = field(default_factory=dict)
    pattern_iteration_count: dict[str, int] = field(default_factory=dict)
    time_budget_skips: int = 0

    # Running performance extremes (not bounded by deque eviction)
    perf_all_time_max_ms: float = 0.0
    perf_all_time_min_ms: float = float("inf")

    # Performance outlier tracking (bounded list)
    performance_outliers: list[PerformanceOutlier] = field(default_factory=list)
    outlier_threshold_ms: float = 0.0  # Dynamically computed from P99


# --- Weighted Schedule ---


def build_weighted_schedule(
    items: Sequence[str],
    weights: Sequence[int],
) -> tuple[str, ...]:
    """Pre-compute a weighted schedule from items.

    Returns a tuple of length sum(weights) where each item appears
    proportional to its weight. Used by round-robin pattern routing
    via select_pattern_round_robin.
    """
    schedule: list[str] = []
    for item, weight in zip(items, weights, strict=True):
        schedule.extend([item] * weight)
    return tuple(schedule)


def select_pattern_round_robin(
    state: BaseFuzzerState,
    schedule: tuple[str, ...],
) -> str:
    """Deterministic round-robin immune to coverage-guided mutation bias.

    libFuzzer's coverage feedback biases FDP-consumed pattern selectors toward
    patterns that maximize coverage-per-second, causing severe weight skew
    (observed: 88% on a 4.5%-weight pattern). Round-robin uses the iteration
    counter to cycle through the weighted schedule, ensuring actual distribution
    matches intended weights exactly.

    All fuzzers increment state.iterations before calling this function,
    so (iterations - 1) maps iteration 1 to schedule index 0.
    """
    return schedule[(state.iterations - 1) % len(schedule)]


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
    pattern: str,
    is_interesting: bool,
) -> None:
    """Track interesting inputs with pattern-stratified FIFO eviction.

    Partitions corpus into per-pattern buckets so every pattern retains
    representative inputs even under high iteration volume. Each pattern
    gets seed_corpus_max_size // num_patterns slots.

    Args:
        state: Fuzzer state to update
        input_key: Hash key for deduplication
        input_data: Raw input bytes to store
        pattern: Pattern that produced this input (for bucket partitioning)
        is_interesting: Whether this input qualifies for corpus inclusion
    """
    if not is_interesting:
        return

    bucket = state.corpus_pattern_buckets.setdefault(pattern, {})

    if input_key in bucket:
        return

    num_patterns = max(1, len(state.pattern_intended_weights) or len(state.corpus_pattern_buckets))
    slots_per_pattern = max(1, state.seed_corpus_max_size // num_patterns)

    if len(bucket) >= slots_per_pattern:
        oldest_key = next(iter(bucket))
        del bucket[oldest_key]
        state.corpus_evictions += 1

    bucket[input_key] = input_data
    state.corpus_entries_added += 1

    # Update flat seed_corpus for backward-compatible reporting
    state.seed_corpus[input_key] = input_data
    if len(state.seed_corpus) > state.seed_corpus_max_size:
        oldest = next(iter(state.seed_corpus))
        del state.seed_corpus[oldest]


# --- Input Hashing ---


def hash_input(data: bytes) -> str:
    """Compute truncated SHA-256 hex digest for corpus deduplication."""
    return hashlib.sha256(data).hexdigest()[:16]


# --- Performance / Memory Tracking ---


def record_memory(state: BaseFuzzerState) -> None:
    """Sample current RSS memory usage (call every ~100 iterations)."""
    current_mb = get_process().memory_info().rss / (1024 * 1024)
    state.memory_history.append(current_mb)


# --- Adaptive Time Budget ---


def update_pattern_cost(state: BaseFuzzerState, pattern: str, elapsed_ms: float) -> None:
    """Update rolling mean cost for a pattern (exponential moving average).

    Args:
        state: Fuzzer state to update
        pattern: Pattern name
        elapsed_ms: Elapsed time for this iteration in milliseconds
    """
    count = state.pattern_iteration_count.get(pattern, 0) + 1
    state.pattern_iteration_count[pattern] = count

    # Exponential moving average with alpha = 0.1 for stability
    alpha = 0.1
    old_mean = state.pattern_mean_cost.get(pattern, elapsed_ms)
    state.pattern_mean_cost[pattern] = old_mean * (1 - alpha) + elapsed_ms * alpha


def check_time_budget(state: BaseFuzzerState, pattern: str, elapsed_ms: float) -> bool:
    """Check if pattern exceeded its time budget.

    Returns True if the pattern should be aborted (exceeded budget).
    Requires at least 100 samples before enforcing budget.

    Args:
        state: Fuzzer state with pattern costs
        pattern: Pattern name to check
        elapsed_ms: Elapsed time so far in milliseconds

    Returns:
        True if pattern exceeded budget and should be aborted
    """
    count = state.pattern_iteration_count.get(pattern, 0)
    if count < 100:
        return False

    mean_cost = state.pattern_mean_cost.get(pattern)
    if mean_cost is None or mean_cost < 1.0:
        return False

    budget_ms = mean_cost * TIME_BUDGET_MULTIPLIER
    if elapsed_ms > budget_ms:
        state.time_budget_skips += 1
        return True

    return False


# --- Performance Outlier Tracking ---


def track_performance_outlier(
    state: BaseFuzzerState,
    elapsed_ms: float,
    pattern: str,
    input_hash: str,
) -> None:
    """Track inputs that exceed the P99 threshold by OUTLIER_THRESHOLD_FACTOR.

    Maintains a bounded list of up to 100 outliers for post-mortem analysis.

    Args:
        state: Fuzzer state to update
        elapsed_ms: Elapsed time in milliseconds
        pattern: Pattern name
        input_hash: Truncated SHA-256 of input
    """
    # Update dynamic threshold every 1000 iterations
    if state.iterations % 1000 == 0 and len(state.performance_history) >= 100:
        quantiles = statistics.quantiles(list(state.performance_history), n=100)
        state.outlier_threshold_ms = quantiles[98] * OUTLIER_THRESHOLD_FACTOR

    if state.outlier_threshold_ms > 0 and elapsed_ms > state.outlier_threshold_ms:
        timestamp = time.strftime("%H:%M:%S")
        entry: PerformanceOutlier = (elapsed_ms, pattern, input_hash, timestamp)

        if len(state.performance_outliers) < 100:
            state.performance_outliers.append(entry)
        elif elapsed_ms > state.performance_outliers[-1][0]:
            # Replace smallest outlier if new one is larger
            state.performance_outliers[-1] = entry
            state.performance_outliers.sort(key=lambda x: -x[0])


def record_iteration_metrics(
    state: BaseFuzzerState,
    pattern: str,
    start_time: float,
    input_data: bytes,
    *,
    is_interesting: bool,
) -> None:
    """Record per-iteration performance, corpus, and adaptive budget metrics.

    Call in the finally block of test_one_input. Includes adaptive time budget
    updates and performance outlier detection.

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

    # Running extremes survive deque eviction
    state.perf_all_time_max_ms = max(state.perf_all_time_max_ms, elapsed_ms)
    state.perf_all_time_min_ms = min(state.perf_all_time_min_ms, elapsed_ms)

    input_hash = hash_input(input_data)
    track_slowest_operation(state, elapsed_ms, pattern, input_hash)
    track_seed_corpus(state, input_hash, input_data, pattern=pattern, is_interesting=is_interesting)

    # Extended tracking
    update_pattern_cost(state, pattern, elapsed_ms)
    track_performance_outlier(state, elapsed_ms, pattern, input_hash)


# --- Stats Building ---


def _add_performance_stats(state: BaseFuzzerState, stats: FuzzStats) -> None:
    """Add performance percentile stats to the stats dictionary.

    Mean/median/percentiles are computed from the bounded deque (recent
    window). Min/max use running extremes that survive deque eviction,
    so they reflect the true all-time campaign extremes.
    """
    if not state.performance_history:
        return

    perf_data = list(state.performance_history)
    n = len(perf_data)
    stats["perf_mean_ms"] = round(statistics.mean(perf_data), 3)
    stats["perf_median_ms"] = round(statistics.median(perf_data), 3)
    stats["perf_min_ms"] = round(state.perf_all_time_min_ms, 3)
    stats["perf_max_ms"] = round(state.perf_all_time_max_ms, 3)
    if n >= 20:
        stats["perf_p95_ms"] = round(statistics.quantiles(perf_data, n=20)[18], 3)
    if n >= 100:
        stats["perf_p99_ms"] = round(statistics.quantiles(perf_data, n=100)[98], 3)


def _add_memory_stats(state: BaseFuzzerState, stats: FuzzStats) -> None:
    """Add memory tracking stats to the stats dictionary.

    memory_delta_mb uses min(observed) as baseline instead of
    initial_memory_mb because Atheris instrumentation inflates RSS at
    import time.  Steady-state RSS settles lower once the fuzzing loop
    begins, so initial_memory_mb would produce a negative delta.
    """
    if not state.memory_history:
        return

    mem_data = list(state.memory_history)
    mem_min = min(mem_data)
    mem_max = max(mem_data)
    stats["memory_mean_mb"] = round(statistics.mean(mem_data), 2)
    stats["memory_peak_mb"] = round(mem_max, 2)
    stats["memory_delta_mb"] = round(mem_max - mem_min, 2)

    if len(mem_data) >= 40:
        first_quarter = mem_data[: len(mem_data) // 4]
        last_quarter = mem_data[-(len(mem_data) // 4) :]
        growth_mb = statistics.mean(last_quarter) - statistics.mean(first_quarter)
        stats["memory_leak_detected"] = 1 if growth_mb > 10.0 else 0
        stats["memory_growth_mb"] = round(growth_mb, 2)
    else:
        stats["memory_leak_detected"] = 0
        stats["memory_growth_mb"] = 0.0


def _add_outlier_stats(state: BaseFuzzerState, stats: FuzzStats) -> None:
    """Add adaptive time budget and performance outlier stats."""
    stats["time_budget_skips"] = state.time_budget_skips
    for pattern, mean_ms in sorted(state.pattern_mean_cost.items()):
        stats[f"pattern_mean_cost_ms_{pattern}"] = round(mean_ms, 3)

    stats["performance_outliers_count"] = len(state.performance_outliers)
    stats["outlier_threshold_ms"] = round(state.outlier_threshold_ms, 3)
    if state.performance_outliers:
        top_outliers = sorted(state.performance_outliers, key=lambda x: -x[0])[:5]
        stats["top_outliers"] = [
            {"ms": round(o[0], 2), "pattern": o[1], "hash": o[2], "time": o[3]}
            for o in top_outliers
        ]


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

    # Fuzzer identification
    if state.fuzzer_name:
        stats["fuzzer_name"] = state.fuzzer_name
    if state.fuzzer_target:
        stats["fuzzer_target"] = state.fuzzer_target

    # Campaign duration and throughput
    if state.campaign_start_time > 0:
        elapsed = time.time() - state.campaign_start_time
        stats["campaign_duration_sec"] = round(elapsed, 1)
        if elapsed > 0 and state.iterations > 0:
            stats["iterations_per_sec"] = round(
                state.iterations / elapsed, 1,
            )

    _add_performance_stats(state, stats)
    _add_memory_stats(state, stats)

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
    corpus_total = sum(len(b) for b in state.corpus_pattern_buckets.values())
    stats["seed_corpus_size"] = corpus_total or len(state.seed_corpus)
    stats["corpus_patterns_retained"] = sum(1 for b in state.corpus_pattern_buckets.values() if b)
    stats["corpus_entries_added"] = state.corpus_entries_added
    stats["corpus_evictions"] = state.corpus_evictions
    stats["corpus_retention_rate"] = round(
        len(state.seed_corpus) / max(1, state.corpus_entries_added),
        8,
    )
    stats["slowest_operations_tracked"] = len(state.slowest_operations)

    # Per-pattern/scenario wall time
    for pattern, total_ms in sorted(state.pattern_wall_time.items()):
        stats[f"{wall_time_prefix}{pattern}"] = round(total_ms, 1)

    _add_outlier_stats(state, stats)
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
    """Emit crash-proof final JSON report to stderr and file.

    Sets status to "complete" for normal exit. Preserves "stopped"
    status if the fuzzer was interrupted by Ctrl+C (set by run_fuzzer
    or per-fuzzer KeyboardInterrupt handlers).

    Args:
        state: Fuzzer state (status finalized here)
        stats: Pre-built stats dictionary (status patched to match)
        report_dir: Directory for the JSON report file
        report_filename: Filename for the JSON report
    """
    if state.status != "stopped":
        state.status = "complete"
    stats["status"] = state.status
    report = json.dumps(stats, sort_keys=True)

    print(
        f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]",
        file=sys.stderr,
        flush=True,
    )

    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / report_filename).write_text(
            report, encoding="utf-8",
        )
    except OSError:
        pass


def emit_checkpoint_report(
    state: BaseFuzzerState,
    stats: FuzzStats,
    report_dir: pathlib.Path,
    report_filename: str,
) -> None:
    """Emit periodic checkpoint JSON to stderr and file.

    Uses [CHECKPOINT-JSON] markers to distinguish from the final
    [SUMMARY-JSON] report emitted at process exit. Does not modify
    state.status (checkpoints are intermediate, not terminal).

    Args:
        state: Fuzzer state (not modified)
        stats: Pre-built stats dictionary
        report_dir: Directory for the JSON report file
        report_filename: Filename for the JSON report
    """
    _ = state  # reserved for future checkpoint-specific logic
    report = json.dumps(stats, sort_keys=True)

    print(
        f"\n[CHECKPOINT-JSON-BEGIN]{report}[CHECKPOINT-JSON-END]",
        file=sys.stderr,
        flush=True,
    )

    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / report_filename).write_text(
            report, encoding="utf-8",
        )
    except OSError:
        pass


# --- FTL Generation Helpers ---


_FTL_ID_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789-"

_FTL_SAFE_VALUE_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    " 0123456789.,!?:;'-"
)


def gen_ftl_identifier(fdp: Any) -> str:
    """Generate a valid FTL identifier: [a-zA-Z][a-zA-Z0-9_-]*.

    Uses FuzzedDataProvider to consume bytes deterministically so
    crash files remain replayable.
    """
    first = chr(ord("a") + fdp.ConsumeIntInRange(0, 25))
    length = fdp.ConsumeIntInRange(0, 15)
    chars = _FTL_ID_CHARS
    n = len(chars) - 1
    rest = "".join(
        chars[fdp.ConsumeIntInRange(0, n)] for _ in range(length)
    )
    return first + rest


def gen_ftl_value(fdp: Any, *, max_length: int = 40) -> str:
    """Generate a safe FTL value (no braces, no newlines).

    Uses FuzzedDataProvider to consume bytes deterministically.
    """
    chars = _FTL_SAFE_VALUE_CHARS
    n = len(chars) - 1
    length = fdp.ConsumeIntInRange(1, max_length)
    return "".join(
        chars[fdp.ConsumeIntInRange(0, n)] for _ in range(length)
    )


# --- Finding Artifacts ---


def write_finding_artifact(
    *,
    findings_dir: pathlib.Path,
    state: BaseFuzzerState,
    source: str,
    s1: str,
    s2: str,
    pattern: str,
    extra_meta: dict[str, Any] | None = None,
) -> None:
    """Write human-readable finding artifacts to disk.

    Writes source/s1/s2 FTL files and a metadata JSON file.
    Increments state.finding_counter. Best-effort (OSError
    silenced). Includes PID in filename prefix to prevent
    collisions when libFuzzer runs multiple forked workers.
    """
    try:
        findings_dir.mkdir(parents=True, exist_ok=True)
        state.finding_counter += 1
        pid = os.getpid()
        prefix = f"finding_p{pid}_{state.finding_counter:04d}"

        findings_dir.joinpath(f"{prefix}_source.ftl").write_text(
            source, encoding="utf-8",
        )
        findings_dir.joinpath(f"{prefix}_s1.ftl").write_text(
            s1, encoding="utf-8",
        )
        findings_dir.joinpath(f"{prefix}_s2.ftl").write_text(
            s2, encoding="utf-8",
        )

        diff_pos = next(
            (
                i
                for i, (a, b) in enumerate(
                    zip(s1, s2, strict=False),
                )
                if a != b
            ),
            min(len(s1), len(s2)),
        )

        encode = "utf-8"
        errors = "surrogatepass"
        meta: dict[str, Any] = {
            "iteration": state.iterations,
            "pattern": pattern,
            "timestamp": datetime.datetime.now(
                tz=datetime.UTC,
            ).isoformat(),
            "source_len": len(source),
            "s1_len": len(s1),
            "s2_len": len(s2),
            "source_hash": hashlib.sha256(
                source.encode(encode, errors=errors),
            ).hexdigest(),
            "s1_hash": hashlib.sha256(
                s1.encode(encode, errors=errors),
            ).hexdigest(),
            "s2_hash": hashlib.sha256(
                s2.encode(encode, errors=errors),
            ).hexdigest(),
            "diff_offset": diff_pos,
        }
        if extra_meta:
            meta.update(extra_meta)

        findings_dir.joinpath(f"{prefix}_meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        print(
            f"\n[FINDING] Artifacts: {findings_dir / prefix}_*",
            file=sys.stderr,
            flush=True,
        )
    except OSError:
        pass  # Finding artifacts are best-effort


# --- Banner ---


def print_fuzzer_banner(
    *,
    title: str,
    target: str,
    state: BaseFuzzerState,
    schedule_len: int,
    mutator: str = "Custom (AST mutation + byte mutation)",
    extra_lines: Sequence[str] = (),
) -> None:
    """Print standard fuzzer startup banner."""
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)
    print(f"Target:     {target}")
    print(f"Checkpoint: Every {state.checkpoint_interval} iterations")
    print(f"Corpus Max: {state.seed_corpus_max_size} entries")
    print(f"GC Cycle:   Every {GC_INTERVAL} iterations")
    sched = f"Round-robin weighted schedule (length: {schedule_len})"
    print(f"Routing:    {sched}")
    print(f"Mutator:    {mutator}")
    for line in extra_lines:
        print(line)
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()
    state.campaign_start_time = time.time()


def _is_multi_worker() -> bool:
    """Detect if libFuzzer will spawn multiple worker processes.

    Checks sys.argv for -workers=N where N > 1.
    """
    for arg in sys.argv:
        if arg.startswith("-workers="):
            try:
                return int(arg.split("=", 1)[1]) > 1
            except ValueError:
                return False
    return False


def run_fuzzer(
    state: BaseFuzzerState,
    *,
    test_one_input: Any,
    custom_mutator: Any | None = None,
) -> None:
    """Run atheris.Fuzz() with graceful KeyboardInterrupt handling.

    Wraps atheris.Setup() + atheris.Fuzz() to suppress the traceback
    on Ctrl+C. Each fuzzer replaces its 2-line Setup/Fuzz with a
    single run_fuzzer() call. The atexit handler (registered by each
    fuzzer) still fires after this returns, emitting the final report.

    Worker model: libFuzzer -workers=N uses fork() to spawn N child
    processes. Each worker gets an independent copy of ``state``, so
    metrics (iterations, findings, pattern_coverage, performance
    history) are per-worker and never aggregated. The JSON report
    file is written by whichever worker exits last, overwriting
    earlier reports. For reliable metrics, use -workers=1 (default).

    Args:
        state: Fuzzer state (status set to "stopped" on interrupt)
        test_one_input: Atheris test callback
        custom_mutator: Optional custom mutator function
    """
    import atheris  # noqa: PLC0415 - fuzz_common importable without atheris

    setup_kwargs: dict[str, Any] = {}
    if custom_mutator is not None:
        setup_kwargs["custom_mutator"] = custom_mutator

    # Disable libFuzzer's SIGINT handler so Python owns the signal.
    # Without this, libFuzzer intercepts Ctrl+C after our KeyboardInterrupt
    # handler and emits a spurious "deadly signal" + empty crash artifact.
    # Only safe in single-worker mode; multi-worker needs libFuzzer's signal
    # handling to manage worker lifecycle (propagate SIGINT to children).
    if not _is_multi_worker() and not any(
        a.startswith("-handle_int=") for a in sys.argv
    ):
        sys.argv.append("-handle_int=0")

    atheris.Setup(
        sys.argv, test_one_input, **setup_kwargs,
    )

    try:
        atheris.Fuzz()
    except KeyboardInterrupt:
        state.status = "stopped"
        print(
            "\n[STOPPED] Fuzzer interrupted by user.",
            file=sys.stderr,
            flush=True,
        )
