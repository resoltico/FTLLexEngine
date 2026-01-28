#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: cache - High-pressure Cache Race & Concurrency
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""High-Pressure Cache Race & Integrity Fuzzer (Atheris).

Targets: ftllexengine.runtime.cache.IntegrityCache (via FluentBundle)
Tests: cache invalidation, key collision, checksum verification, write-once semantics,
       multi-threaded resolution synchronization, memory limits, error limits.
"""

from __future__ import annotations

import atexit
import heapq
import json
import logging
import os
import queue
import statistics
import sys
import threading
import time
from collections import deque

import psutil

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str]
type ThreadOp = dict[str, str | None]
type ThreadData = dict[str, list[ThreadOp]]

_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}

# Performance profiling globals
performance_history: deque[float] = deque(maxlen=1000)
memory_history: deque[float] = deque(maxlen=100)
# Heapq min-heaps: (value, data) tuples for efficient top-N tracking
slowest_operations: list[tuple[float, str]] = []
fastest_operations: list[tuple[float, str]] = []
error_counts: dict[str, int] = {}
pattern_coverage: set[str] = set()

# Cache-specific metrics
cache_hit_rates: deque[float] = deque(maxlen=100)
corruption_events: dict[str, int] = {}
write_conflict_counts: int = 0
oversize_skip_counts: int = 0
error_bloat_counts: int = 0

# Process handle (created once, reused for all iterations)
_process: psutil.Process = psutil.Process(os.getpid())

# Seed corpus management
seed_corpus: list[bytes] = []
interesting_inputs: list[tuple[bytes, str]] = []

def _add_to_seed_corpus(data: bytes, reason: str) -> None:
    """Add input to seed corpus if it's interesting."""
    if len(seed_corpus) < 1000:  # Limit corpus size
        seed_corpus.append(data)
        interesting_inputs.append((data, reason))

def _is_interesting_input(
    config_str: str,
    duration: float,
    cache_stats: dict[str, int],
    exception: Exception | None = None,
) -> str | None:
    """Determine if input is interesting for corpus expansion."""
    reasons = []

    # Exception-triggering inputs
    if exception:
        reasons.append(f"exception_{type(exception).__name__}")

    # Slow operations
    if duration > 0.05:  # >50ms
        reasons.append("slow_operation")

    # Unique pattern (first 30 chars of config)
    pattern = config_str[:30]
    if pattern not in pattern_coverage:
        pattern_coverage.add(pattern)
        reasons.append("new_pattern")

    # Cache performance edge cases
    if cache_stats.get("corruption", 0) > 0:
        reasons.append("corruption_detected")

    if cache_stats.get("write_conflicts", 0) > 0:
        reasons.append("write_once_conflict")

    if cache_stats.get("oversize_skips", 0) > 10:
        reasons.append("memory_pressure")

    if cache_stats.get("error_bloat", 0) > 10:
        reasons.append("error_bloat")

    # Low hit ratio (inefficient cache)
    hit_ratio = (
        cache_stats["hits"] / (cache_stats["hits"] + cache_stats["misses"])
        if (cache_stats["hits"] + cache_stats["misses"]) > 0
        else 0
    )
    if hit_ratio < 0.3:
        reasons.append("low_hit_ratio")

    return reasons[0] if reasons else None

def _get_performance_summary() -> dict[str, float]:
    """Get comprehensive performance statistics."""
    if not performance_history:
        return {}

    return {
        "mean": statistics.mean(performance_history),
        "median": statistics.median(performance_history),
        "stdev": (
            statistics.stdev(performance_history) if len(performance_history) > 1 else 0
        ),
        "min": min(performance_history),
        "max": max(performance_history),
        "p95": (
            statistics.quantiles(performance_history, n=20)[18]
            if len(performance_history) >= 20
            else max(performance_history)
        ),
        "p99": (
            statistics.quantiles(performance_history, n=100)[98]
            if len(performance_history) >= 100
            else max(performance_history)
        ),
        "memory_mean": statistics.mean(memory_history) if memory_history else 0,
        "memory_max": max(memory_history) if memory_history else 0,
    }

def _emit_final_report() -> None:
    """Emit comprehensive fuzzing statistics."""
    perf_summary = _get_performance_summary()

    # Extract top 5 slowest/fastest (heapq stores as (duration, config) tuples)
    slowest_top5 = [(cfg, dur) for dur, cfg in heapq.nlargest(5, slowest_operations)]
    fastest_top5 = [(cfg, -dur) for dur, cfg in heapq.nsmallest(5, fastest_operations)]

    # Compute average hit rate
    avg_hit_rate = statistics.mean(cache_hit_rates) if cache_hit_rates else 0

    stats = {
        "status": _fuzz_stats["status"],
        "iterations": _fuzz_stats["iterations"],
        "findings": _fuzz_stats["findings"],
        "slow_operations": _fuzz_stats.get("slow_operations", 0),
        "coverage_estimate": (
            "high" if int(_fuzz_stats["iterations"]) > 1000000 else "medium"
        ),
        "performance": perf_summary,
        "pattern_coverage": len(pattern_coverage),
        "error_types": error_counts,
        "slowest_operations": slowest_top5,
        "fastest_operations": fastest_top5,
        "cache_avg_hit_rate": avg_hit_rate,
        "cache_corruption_events": corruption_events,
        "cache_write_conflicts": write_conflict_counts,
        "cache_oversize_skips": oversize_skip_counts,
        "cache_error_bloat_skips": error_bloat_counts,
        "seed_corpus_size": len(seed_corpus),
        "interesting_inputs": len(interesting_inputs),
        "memory_leaks_detected": _fuzz_stats.get("memory_leaks", 0),
    }
    report = json.dumps(stats, default=str)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)

def _update_performance_stats(duration: float, config_str: str, memory_mb: float) -> None:
    """Update performance statistics with advanced analysis."""
    performance_history.append(duration)
    memory_history.append(memory_mb)

    # Track slowest operations using min-heap (maintain top 10 largest)
    if len(slowest_operations) < 10:
        heapq.heappush(slowest_operations, (duration, config_str[:50]))
    elif duration > slowest_operations[0][0]:
        heapq.heapreplace(slowest_operations, (duration, config_str[:50]))

    # Track fastest operations using max-heap (maintain top 10 smallest)
    neg_duration = -duration
    if len(fastest_operations) < 10:
        heapq.heappush(fastest_operations, (neg_duration, config_str[:50]))
    elif neg_duration > fastest_operations[0][0]:
        heapq.heapreplace(fastest_operations, (neg_duration, config_str[:50]))

    # Track patterns
    pattern_coverage.add(config_str[:30])

atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    sys.exit(1)

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.integrity import (
        CacheCorruptionError,
        DataIntegrityError,
        WriteConflictError,
    )
    from ftllexengine.runtime.bundle import FluentBundle

TEST_LOCALES = ["en-US", "de-DE", "lv-LV", "ar-SA", "ja-JP", "root"]

def generate_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate locale for bundle creation.

    Weighted 90% valid / 10% invalid to ensure cache logic is exercised.
    """
    # 90% valid locales
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(TEST_LOCALES)
    # 10% malformed locales
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))

def generate_ftl_resource(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate FTL resource for cache stress testing.

    Focus on patterns that exercise cache:
    - Variable interpolation (cache key variation)
    - Multiple messages (cache capacity stress)
    - Complex patterns (memory weight variation)
    """
    # Weighted strategy: 80% valid, 20% edge cases
    strategy_type = fdp.ConsumeIntInRange(0, 9)

    if strategy_type <= 7:  # 80% valid
        valid_strategies = [
            # Simple messages with variables
            lambda: "\n".join([
                f"msg{i} = Value {i} {{ $var{i % 3} }}"
                for i in range(fdp.ConsumeIntInRange(5, 15))
            ]) + "\n",
            # Messages with attributes (cache key variation)
            lambda: "\n".join([
                f"msg{i} = Value\n    .tooltip = Tooltip {i}"
                for i in range(fdp.ConsumeIntInRange(3, 10))
            ]) + "\n",
            # Select expressions (complex patterns)
            lambda: "\n".join([
                f"msg{i} = {{ $count ->\n    [one] One\n   *[other] Many\n}}"
                for i in range(fdp.ConsumeIntInRange(3, 8))
            ]) + "\n",
            # Message references (resolver stress)
            lambda: "\n".join([
                f"msg{i} = {{ msg{(i + 1) % 5} }}"
                for i in range(5)
            ]) + "msg5 = Final\n",
            # Terms (namespace variation)
            lambda: "\n".join([
                f"-term{i} = Term {i}\nmsg{i} = {{ -term{i} }}"
                for i in range(fdp.ConsumeIntInRange(3, 8))
            ]) + "\n",
        ]
        return fdp.PickValueInList(valid_strategies)()

    # 20% edge cases
    edge_strategies = [
        # Very long values (memory weight stress)
        lambda: f"msg = {'x' * fdp.ConsumeIntInRange(1000, 5000)}\n",
        # Many variables (key complexity)
        lambda: (
            "msg = "
            + " ".join([f"{{ $var{i} }}" for i in range(fdp.ConsumeIntInRange(5, 20))])
            + "\n"
        ),
        # Circular reference (resolver error stress)
        lambda: "msg_a = { msg_b }\nmsg_b = { msg_a }\n",
        # Empty resource
        lambda: "\n",
    ]
    return fdp.PickValueInList(edge_strategies)()

def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: Stress-test cache under concurrent access."""
    # pylint: disable=global-statement
    global write_conflict_counts, oversize_skip_counts, error_bloat_counts  # noqa: PLW0603

    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # Local counters for thread-safe aggregation
    local_write_conflicts = 0
    local_corruption_events: dict[str, int] = {}

    # Generate cache configuration (vary all parameters)
    cache_size = fdp.ConsumeIntInRange(1, 50)
    max_entry_weight = fdp.ConsumeIntInRange(100, 10000)
    max_errors_per_entry = fdp.ConsumeIntInRange(1, 100)
    write_once = fdp.ConsumeBool()
    strict_mode = fdp.ConsumeBool()
    enable_audit = fdp.ConsumeBool()

    # Generate locale
    locale = generate_locale(fdp)

    # Create config string for tracking
    config_str = (
        f"cache={cache_size},weight={max_entry_weight},errors={max_errors_per_entry},"
        f"write_once={write_once},strict={strict_mode},audit={enable_audit},"
        f"locale={locale}"
    )

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
    except (ValueError, TypeError):
        # Invalid locale or config, skip
        return

    # Generate FTL resource
    ftl = generate_ftl_resource(fdp)

    # Fast-path rejection: empty resource
    if not ftl.strip():
        return

    # Add resource to bundle
    try:
        bundle.add_resource(ftl)
    except (ValueError, TypeError):
        # Invalid FTL or duplicate IDs, skip
        return

    # Track performance and memory
    start_time = time.perf_counter()
    start_memory = _process.memory_info().rss / 1024 / 1024  # MB

    # Pre-generate thread data (FuzzedDataProvider is NOT thread-safe)
    num_threads = fdp.ConsumeIntInRange(2, 8)
    num_operations = fdp.ConsumeIntInRange(10, 50)

    thread_data_list: list[ThreadData] = []
    for _ in range(num_threads):
        # Each thread gets its own data
        thread_ops: list[ThreadOp] = []
        for _ in range(num_operations):
            msg_idx = fdp.ConsumeIntInRange(0, 9)
            var_val = fdp.ConsumeUnicodeNoSurrogates(5)
            attr = (
                fdp.PickValueInList(["tooltip", "aria-label", None])
                if fdp.ConsumeBool()
                else None
            )
            thread_ops.append({
                "msg_id": f"msg{msg_idx}",
                "var_val": var_val,
                "attribute": attr,
            })

        thread_data_list.append({"operations": thread_ops})

    # Thread-safe error collection
    error_queue: queue.Queue[str] = queue.Queue()
    # Thread-safe counters using queues
    write_conflict_queue: queue.Queue[int] = queue.Queue()
    corruption_event_queue: queue.Queue[tuple[str, int]] = queue.Queue()

    def worker(worker_data: ThreadData) -> None:
        """Worker thread: perform cache operations."""
        nonlocal local_write_conflicts, local_corruption_events
        ops = worker_data["operations"]
        for op in ops:
            try:
                msg_id = str(op["msg_id"])
                var_val = str(op["var_val"])
                attribute = op.get("attribute")

                # Format message (exercises cache)
                # format_pattern always returns str, so no need for type check
                _val, _errs = bundle.format_pattern(
                    msg_id,
                    {"var0": var_val, "var1": var_val, "var2": var_val},
                    attribute=attribute,
                )

            except CacheCorruptionError as e:
                # Expected in strict mode with corrupted cache
                corruption_event_queue.put((str(e)[:50], 1))
            except WriteConflictError:
                # Expected in write_once mode
                write_conflict_queue.put(1)
            except DataIntegrityError:
                # Expected: strict mode integrity violations (MESSAGE_NOT_FOUND, etc.)
                # Do NOT report as finding - this is spec-compliant behavior
                pass
            except (ValueError, TypeError, KeyError):
                # Expected: message not found, invalid args, etc.
                pass
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Fuzzing: catch all unexpected exceptions as findings
                error_queue.put(f"Worker exception: {type(e).__name__}: {e}")

    # Spawn threads
    threads = [threading.Thread(target=worker, args=(td,)) for td in thread_data_list]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Collect errors from queue (thread-safe)
    errors = []
    while not error_queue.empty():
        errors.append(error_queue.get())

    # Aggregate thread-local counters
    while not write_conflict_queue.empty():
        local_write_conflicts += write_conflict_queue.get()

    while not corruption_event_queue.empty():
        key, count = corruption_event_queue.get()
        local_corruption_events[key] = local_corruption_events.get(key, 0) + count

    # Update global counters
    write_conflict_counts += local_write_conflicts
    for key, count in local_corruption_events.items():
        corruption_events[key] = corruption_events.get(key, 0) + count

    # Monitor for performance regressions
    duration = time.perf_counter() - start_time
    end_memory = _process.memory_info().rss / 1024 / 1024  # MB
    memory_delta = end_memory - start_memory

    # Extract cache statistics (accessing cache internals for observability)
    cache = bundle._cache  # Access private attribute for testing
    if cache is not None:
        cache_stats = {
            "hits": cache._hits,
            "misses": cache._misses,
            "corruption": cache._corruption_detected,
            "write_conflicts": cache._idempotent_writes,
            "oversize_skips": cache._oversize_skips,
            "error_bloat": cache._error_bloat_skips,
        }

        # Track global counts
        oversize_skip_counts += cache._oversize_skips
        error_bloat_counts += cache._error_bloat_skips

        # Compute hit ratio
        hit_ratio = (
            cache_stats["hits"] / (cache_stats["hits"] + cache_stats["misses"])
            if (cache_stats["hits"] + cache_stats["misses"]) > 0
            else 0
        )
        cache_hit_rates.append(hit_ratio)
    else:
        # Cache was not enabled (shouldn't happen, but handle gracefully)
        cache_stats = {
            "hits": 0,
            "misses": 0,
            "corruption": 0,
            "write_conflicts": 0,
            "oversize_skips": 0,
            "error_bloat": 0,
        }

    # Update performance stats
    _update_performance_stats(duration, config_str, end_memory)

    # Add interesting inputs to seed corpus
    interesting_reason = _is_interesting_input(config_str, duration, cache_stats)
    if interesting_reason:
        _add_to_seed_corpus(data, interesting_reason)

    # Track slow operations
    if duration > 0.05:  # >50ms
        slow_count = int(_fuzz_stats.get("slow_operations", 0)) + 1
        _fuzz_stats["slow_operations"] = slow_count

    # Detect memory leaks (rough heuristic)
    if memory_delta > 50:  # >50MB increase
        leak_count = int(_fuzz_stats.get("memory_leaks", 0)) + 1
        _fuzz_stats["memory_leaks"] = leak_count

    # Report findings
    if errors:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        for error in errors:
            error_type = error.split(":")[0]
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        raise RuntimeError("\n".join(errors))

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
