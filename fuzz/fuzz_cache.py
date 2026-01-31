#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: cache - High-pressure Cache Race & Concurrency
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""High-Pressure Cache Race and Integrity Fuzzer (Atheris).

Targets: ftllexengine.runtime.cache.IntegrityCache (via FluentBundle)
Tests cache invalidation, key collision, checksum verification, write-once
semantics, multi-threaded resolution synchronization, memory limits, and
error limits.

Concern boundary: This fuzzer stress-tests the IntegrityCache subsystem by
systematically varying all cache constructor parameters (size, entry weight,
error limits, write-once, audit mode) under concurrent multi-threaded access.
This is distinct from the runtime fuzzer which tests the full resolver stack
with fixed cache configs and only 2 threads.

Metrics:
- Cache hit/miss ratios and efficiency
- Write conflicts and corruption events
- Oversize skip and error bloat counts
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Thread concurrency stress (2-8 threads)
- Seed corpus management

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
import queue
import statistics
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

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
type ThreadOp = dict[str, str | None]


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

    # Coverage tracking
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Slowest operations (min-heap for top 10)
    slowest_operations: list[tuple[float, str]] = field(default_factory=list)

    # Seed corpus
    seed_corpus: dict[str, bytes] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Cache-specific metrics
    cache_hit_rates: deque[float] = field(default_factory=lambda: deque(maxlen=10000))
    write_conflict_counts: int = 0
    oversize_skip_counts: int = 0
    error_bloat_counts: int = 0
    corruption_events: dict[str, int] = field(default_factory=dict)
    slow_operations: int = 0

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

    # Pattern coverage
    stats["patterns_tested"] = len(_state.pattern_coverage)
    for pattern, count in sorted(_state.pattern_coverage.items()):
        stats[f"pattern_{pattern}"] = count

    # Error distribution
    stats["error_types"] = len(_state.error_counts)
    for error_type, count in sorted(_state.error_counts.items()):
        clean_key = error_type[:50].replace("<", "").replace(">", "")
        stats[f"error_{clean_key}"] = count

    # Cache-specific metrics
    stats["cache_write_conflicts"] = _state.write_conflict_counts
    stats["cache_oversize_skips"] = _state.oversize_skip_counts
    stats["cache_error_bloat_skips"] = _state.error_bloat_counts
    stats["slow_operations"] = _state.slow_operations

    if _state.cache_hit_rates:
        stats["cache_avg_hit_rate"] = round(statistics.mean(_state.cache_hit_rates), 3)

    for event, count in sorted(_state.corruption_events.items()):
        stats[f"corruption_{event[:40]}"] = count

    # Corpus stats
    stats["seed_corpus_size"] = len(_state.seed_corpus)
    stats["corpus_entries_added"] = _state.corpus_entries_added
    stats["slowest_operations_tracked"] = len(_state.slowest_operations)

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
        report_file = pathlib.Path(".fuzz_corpus") / "cache" / "fuzz_cache_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass  # Best-effort file write


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.integrity import (
        CacheCorruptionError,
        DataIntegrityError,
        WriteConflictError,
    )
    from ftllexengine.runtime.bundle import FluentBundle

# --- Constants ---
TEST_LOCALES: Sequence[str] = (
    "en-US", "de-DE", "lv-LV", "ar-SA", "ja-JP", "zh-CN", "root",
)

_MSG_IDENTIFIERS: Sequence[str] = (
    "msg0", "msg1", "msg2", "msg3", "msg4",
    "msg5", "msg6", "msg7", "msg8", "msg9",
)

_ATTR_NAMES: Sequence[str] = (
    "tooltip", "aria-label", "placeholder", "title",
)


def _generate_deep_args(
    fdp: atheris.FuzzedDataProvider,
) -> dict[str, object]:
    """Generate deeply nested / unhashable args to stress _make_hashable().

    Produces args with nested dicts, lists, mixed types, and edge-case
    values that exercise every branch of the cache key conversion logic.
    """
    args: dict[str, object] = {}
    num_keys = fdp.ConsumeIntInRange(1, 8)

    for i in range(num_keys):
        if fdp.remaining_bytes() < 2:
            args[f"var{i}"] = i
            continue

        val_type = fdp.ConsumeIntInRange(0, 8)
        match val_type:
            case 0:
                # Nested dict (2-4 levels deep)
                depth = fdp.ConsumeIntInRange(2, 4)
                inner: object = fdp.ConsumeUnicodeNoSurrogates(5)
                for _ in range(depth):
                    inner = {"k": inner}
                args[f"var{i}"] = inner
            case 1:
                # List of mixed types
                args[f"var{i}"] = [
                    fdp.ConsumeInt(2),
                    fdp.ConsumeUnicodeNoSurrogates(3),
                    fdp.ConsumeBool(),
                ]
            case 2:
                # Nested list of lists
                args[f"var{i}"] = [[1, 2], [3, [4, 5]]]
            case 3:
                # Float edge cases (-0.0, inf, nan)
                args[f"var{i}"] = fdp.PickValueInList(
                    [0.0, -0.0, float("inf"), float("-inf"), float("nan")]
                )
            case 4:
                # Boolean (hash collision with int: hash(True)==hash(1))
                args[f"var{i}"] = fdp.ConsumeBool()
            case 5:
                # Dict with tuple-like keys stress
                args[f"var{i}"] = {
                    "a": [1, {"b": 2}],
                    "c": fdp.ConsumeUnicodeNoSurrogates(3),
                }
            case 6:
                # Empty containers
                args[f"var{i}"] = fdp.PickValueInList([[], {}, ""])
            case 7:
                # Set (unhashable in dicts by default)
                args[f"var{i}"] = {1, 2, 3}
            case _:
                # Large nested structure
                args[f"var{i}"] = {"l": list(range(20)), "d": {"x": {"y": "z"}}}

    return args


def _generate_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(TEST_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))


def _generate_ftl_resource(  # noqa: PLR0911, PLR0912
    fdp: atheris.FuzzedDataProvider,
) -> tuple[str, str]:
    """Generate FTL resource for cache stress testing.

    13 strategies targeting distinct cache behaviors.

    Returns:
        (pattern_name, ftl_source)
    """
    weights = [10, 8, 8, 8, 8, 6, 6, 6, 6, 6, 12, 6, 10]  # 13 strategies
    total_weight = sum(weights)
    choice = fdp.ConsumeIntInRange(0, total_weight - 1)

    cumulative = 0
    strategy = 0
    for i, weight in enumerate(weights):
        cumulative += weight
        if choice < cumulative:
            strategy = i
            break

    match strategy:
        case 0:  # Variable messages (cache key variation)
            n = fdp.ConsumeIntInRange(5, 15)
            ftl = "\n".join(
                f"msg{i} = Value {i} {{ $var{i % 3} }}" for i in range(n)
            ) + "\n"
            return ("variable_messages", ftl)

        case 1:  # Attribute messages (cache key with attribute)
            n = fdp.ConsumeIntInRange(3, 10)
            ftl = "\n".join(
                f"msg{i} = Value\n    .tooltip = Tooltip {i}\n    .title = Title {i}"
                for i in range(n)
            ) + "\n"
            return ("attribute_messages", ftl)

        case 2:  # Select expressions (complex patterns)
            n = fdp.ConsumeIntInRange(3, 8)
            ftl = "\n".join(
                f"msg{i} = {{ $count ->\n    [one] One\n   *[other] Many\n}}"
                for i in range(n)
            ) + "\n"
            return ("select_expressions", ftl)

        case 3:  # Message references (resolver stress)
            ftl = "\n".join(
                f"msg{i} = {{ msg{(i + 1) % 5} }}" for i in range(5)
            ) + "\nmsg5 = Final\n"
            return ("message_references", ftl)

        case 4:  # Terms (namespace variation)
            n = fdp.ConsumeIntInRange(3, 8)
            ftl = "\n".join(
                f"-term{i} = Term {i}\nmsg{i} = {{ -term{i} }}" for i in range(n)
            ) + "\n"
            return ("term_references", ftl)

        case 5:  # Very long values (memory weight stress)
            size = fdp.ConsumeIntInRange(1000, 5000)
            ftl = f"msg0 = {'x' * size}\n"
            return ("long_values", ftl)

        case 6:  # Many variables (key complexity)
            n = fdp.ConsumeIntInRange(5, 20)
            placeables = " ".join(f"{{ $var{i} }}" for i in range(n))
            ftl = f"msg0 = {placeables}\n"
            return ("many_variables", ftl)

        case 7:  # Circular references (resolver error stress)
            ftl = "msg0 = { msg1 }\nmsg1 = { msg0 }\n"
            return ("circular_refs", ftl)

        case 8:  # Empty / minimal resource
            ftl = fdp.PickValueInList([
                "\n",
                "# comment only\n",
                "msg0 = \n",
                "msg0 = x\n",
            ])
            return ("minimal_resource", ftl)

        case 9:  # Hotspot pattern (same message repeated)
            ftl = "msg0 = Hotspot {{ $var0 }}\nmsg1 = Other\n"
            return ("hotspot", ftl)

        case 10:  # Raw bytes pass-through (let libFuzzer mutations drive)
            raw = fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, 500))
            return ("raw_bytes", raw)

        case 11:  # Many small messages (cache capacity stress)
            n = fdp.ConsumeIntInRange(20, 50)
            ftl = "\n".join(f"msg{i} = v{i}" for i in range(n)) + "\n"
            return ("capacity_stress", ftl)

        case 12:  # Deep/unhashable args (stress _make_hashable)
            n = fdp.ConsumeIntInRange(3, 8)
            placeables = " ".join(f"{{ $var{i} }}" for i in range(n))
            ftl = f"msg0 = {placeables}\n"
            return ("deep_args", ftl)

        case _:
            return ("fallback", "msg0 = fallback\n")


def _track_slowest_operation(duration_ms: float, config_str: str) -> None:
    """Track top 10 slowest operations using min-heap."""
    if len(_state.slowest_operations) < 10:
        heapq.heappush(_state.slowest_operations, (duration_ms, config_str[:50]))
    elif duration_ms > _state.slowest_operations[0][0]:
        heapq.heapreplace(_state.slowest_operations, (duration_ms, config_str[:50]))


def _track_seed_corpus(data: bytes, pattern: str, duration_ms: float) -> None:
    """Track interesting inputs for seed corpus with LRU-like eviction."""
    is_interesting = (
        duration_ms > 50.0
        or "circular" in pattern
        or "raw_bytes" in pattern
        or "capacity" in pattern
    )

    if is_interesting:
        input_hash = hashlib.sha256(data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = data
            _state.corpus_entries_added += 1


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: Stress-test cache under concurrent access.

    Observability:
    - Performance: Tracks timing per iteration
    - Memory: Tracks RSS via psutil (every 100 iterations)
    - Cache: Hit/miss ratios, write conflicts, corruption events
    - Patterns: Coverage of 13 FTL generation strategies
    - Corpus: Interesting inputs (slow/circular/raw/capacity)
    """
    # Initialize memory baseline on first iteration
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic report write for shell script parsing
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    fdp = atheris.FuzzedDataProvider(data)

    # Generate cache configuration (vary all parameters)
    cache_size = fdp.ConsumeIntInRange(1, 50)
    max_entry_weight = fdp.ConsumeIntInRange(100, 10000)
    max_errors_per_entry = fdp.ConsumeIntInRange(1, 100)
    write_once = fdp.ConsumeBool()
    strict_mode = fdp.ConsumeBool()
    enable_audit = fdp.ConsumeBool()

    # Generate locale
    locale = _generate_locale(fdp)

    # Generate FTL resource (13 strategies with weighted selection)
    pattern_name, ftl = _generate_ftl_resource(fdp)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    # Pre-generate deep args for _make_hashable stress (fdp not thread-safe)
    deep_args: dict[str, object] | None = None
    if pattern_name == "deep_args":
        deep_args = _generate_deep_args(fdp)

    # Create bundle with cache
    try:
        bundle = FluentBundle(
            locale,
            enable_cache=True,
            cache_size=cache_size,
            cache_max_entry_weight=max_entry_weight,
            cache_max_errors_per_entry=max_errors_per_entry,
            cache_write_once=write_once,
            strict=strict_mode,
            cache_enable_audit=enable_audit,
        )
    except (ValueError, TypeError, DataIntegrityError):
        return  # Invalid locale or config

    # Fast-path rejection: empty resource
    if not ftl.strip():
        return

    # Add resource to bundle
    try:
        bundle.add_resource(ftl)
    except (ValueError, TypeError, DataIntegrityError):
        return  # Invalid FTL or strict-mode syntax errors

    # Performance timing
    start_time = time.perf_counter()

    # Pre-generate thread data (FuzzedDataProvider is NOT thread-safe)
    num_threads = fdp.ConsumeIntInRange(2, 8)
    num_operations = fdp.ConsumeIntInRange(10, 50)

    thread_data_list: list[list[ThreadOp]] = []
    for _ in range(num_threads):
        thread_ops: list[ThreadOp] = []
        for _ in range(num_operations):
            if fdp.remaining_bytes() < 4:
                thread_ops.append({
                    "msg_id": "msg0",
                    "var_val": "default",
                    "attribute": None,
                })
                continue

            msg_idx = fdp.ConsumeIntInRange(0, 9)
            var_val = fdp.ConsumeUnicodeNoSurrogates(5)
            attr: str | None = (
                fdp.PickValueInList(list(_ATTR_NAMES))
                if fdp.ConsumeBool()
                else None
            )
            thread_ops.append({
                "msg_id": f"msg{msg_idx}",
                "var_val": var_val,
                "attribute": attr,
            })

        thread_data_list.append(thread_ops)

    # Thread-safe error collection
    error_queue: queue.Queue[str] = queue.Queue()
    write_conflict_queue: queue.Queue[int] = queue.Queue()
    corruption_event_queue: queue.Queue[tuple[str, int]] = queue.Queue()

    def worker(ops: list[ThreadOp]) -> None:
        """Execute cache operations in a worker thread."""
        for op in ops:
            try:
                msg_id = str(op["msg_id"])
                var_val = str(op["var_val"])
                attribute = op.get("attribute")

                # Use deep args when testing _make_hashable, else simple args
                fmt_args: Any = (
                    deep_args
                    if deep_args is not None
                    else {"var0": var_val, "var1": var_val, "var2": var_val,
                          "count": 1, "var": var_val}
                )
                bundle.format_pattern(
                    msg_id,
                    cast(dict[str, Any], fmt_args),
                    attribute=attribute,
                )

            except CacheCorruptionError as e:
                corruption_event_queue.put((str(e)[:50], 1))
            except WriteConflictError:
                write_conflict_queue.put(1)
            except DataIntegrityError:
                # Expected: strict mode integrity violations
                pass
            except (ValueError, TypeError, KeyError):
                # Expected: message not found, invalid args
                pass
            except (RecursionError, MemoryError, FrozenFluentError):
                # Depth guard / memory safety
                pass
            except Exception as e:  # pylint: disable=broad-exception-caught
                error_queue.put(f"Worker exception: {type(e).__name__}: {e}")

    # Spawn threads
    threads = [
        threading.Thread(target=worker, args=(ops,))
        for ops in thread_data_list
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        if t.is_alive():
            _state.error_counts["thread_timeout"] = (
                _state.error_counts.get("thread_timeout", 0) + 1
            )

    # Performance tracking
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    _state.performance_history.append(elapsed_ms)

    # Collect errors from queues
    errors: list[str] = []
    while not error_queue.empty():
        errors.append(error_queue.get())

    local_write_conflicts = 0
    while not write_conflict_queue.empty():
        local_write_conflicts += write_conflict_queue.get()
    _state.write_conflict_counts += local_write_conflicts

    while not corruption_event_queue.empty():
        key, count = corruption_event_queue.get()
        _state.corruption_events[key] = (
            _state.corruption_events.get(key, 0) + count
        )

    # Extract cache statistics
    cache = bundle._cache
    if cache is not None:
        total = cache._hits + cache._misses
        if total > 0:
            hit_ratio = cache._hits / total
            _state.cache_hit_rates.append(hit_ratio)
        _state.oversize_skip_counts += cache._oversize_skips
        _state.error_bloat_counts += cache._error_bloat_skips
    # Track slow operations
    if elapsed_ms > 50.0:
        _state.slow_operations += 1

    # Per-pattern wall time accumulation
    _state.pattern_wall_time[pattern_name] = (
        _state.pattern_wall_time.get(pattern_name, 0.0) + elapsed_ms
    )

    _track_slowest_operation(elapsed_ms, f"{pattern_name}_{locale}")
    _track_seed_corpus(data, pattern_name, elapsed_ms)

    # Memory tracking (every 100 iterations to reduce overhead)
    if _state.iterations % 100 == 0:
        current_memory_mb = _get_process().memory_info().rss / (1024 * 1024)
        _state.memory_history.append(current_memory_mb)

    # Report findings
    if errors:
        _state.findings += 1
        for error in errors:
            error_type = error.split(":")[0][:50]
            _state.error_counts[error_type] = (
                _state.error_counts.get(error_type, 0) + 1
            )
        raise RuntimeError("\n".join(errors))


def main() -> None:
    """Run the cache fuzzer with optional --help."""
    parser = argparse.ArgumentParser(
        description="Cache race & integrity fuzzer using Atheris/libFuzzer",
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
    print("Cache Race & Integrity Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     ftllexengine.runtime.cache.IntegrityCache")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Threads:    2-8 concurrent workers per iteration")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
