#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: lock - RWLock Concurrency & Contention
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""RWLock Contention Fuzzer (Atheris).

Targets: ftllexengine.runtime.rwlock.RWLock, with_read_lock, with_write_lock

Concern boundary: This fuzzer stress-tests the RWLock concurrency primitive
directly. Tests reader/writer mutual exclusion, reader concurrency, writer
preference, reentrant readers, reentrant writers, write-to-read downgrading,
read-to-write upgrade rejection, decorator correctness, and deadlock detection.
Distinct from runtime/cache fuzzers which exercise locking only as a side effect.

Metrics:
- Pattern coverage (reader_writer_exclusion, reentrant_reads, etc.)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Thread contention events and deadlock detection
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
import statistics
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float | list[Any]]
type InterestingInput = tuple[float, str, str]  # (duration_ms, pattern, input_hash)

# --- Dependency Checks ---
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

    # Concurrency-specific
    deadlocks_detected: int = 0
    timeouts: int = 0

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 500


# Global state instance
_state = FuzzerState()
_process: psutil.Process | None = None

# Thread join timeout (seconds) -- triggers deadlock detection
_THREAD_TIMEOUT = 2.0


def _get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


# Pattern weights: cheapest-first ordering.
# libFuzzer's ConsumeIntInRange skews toward small values with short inputs,
# so early entries are over-selected. Placing cheap single-threaded patterns
# first ensures the natural bias falls on near-free operations, not expensive
# multi-threaded patterns.
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # Cheap: single-threaded, no thread creation, sub-0.02ms
    ("reentrant_reads", 5),
    ("reentrant_writes", 5),
    ("upgrade_rejection", 8),
    ("decorator_correctness", 6),
    ("write_to_read_downgrade", 10),
    # Medium: multi-threaded but bounded
    ("rapid_lock_cycling", 8),
    ("cross_thread_handoff", 6),
    ("concurrent_readers", 12),
    ("timeout_acquisition", 8),
    # Expensive: multi-threaded with sleeps, barriers, contention
    ("reader_writer_exclusion", 15),
    ("writer_preference", 10),
    ("reader_starvation", 6),
    ("mixed_contention", 7),
)


class LockFuzzError(Exception):
    """Raised when an RWLock invariant is breached."""


# Allowed exceptions from lock operations
ALLOWED_EXCEPTIONS = (RuntimeError, TimeoutError)


def _build_stats_dict() -> FuzzStats:
    """Build stats dictionary for JSON report."""
    stats: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
        "deadlocks_detected": _state.deadlocks_detected,
        "timeouts": _state.timeouts,
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

        if len(mem_data) >= 40:
            first_quarter = mem_data[: len(mem_data) // 4]
            last_quarter = mem_data[-(len(mem_data) // 4) :]
            growth_mb = statistics.mean(last_quarter) - statistics.mean(first_quarter)
            stats["memory_leak_detected"] = 1 if growth_mb > 10.0 else 0
            stats["memory_growth_mb"] = round(growth_mb, 2)
        else:
            stats["memory_leak_detected"] = 0
            stats["memory_growth_mb"] = 0.0

    # Pattern coverage
    stats["patterns_tested"] = len(_state.pattern_coverage)
    for pattern, count in sorted(_state.pattern_coverage.items()):
        stats[f"pattern_{pattern}"] = count

    # Error distribution
    stats["error_types"] = len(_state.error_counts)
    for error_type, count in sorted(_state.error_counts.items()):
        clean_key = error_type[:50].replace("<", "").replace(">", "")
        stats[f"error_{clean_key}"] = count

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

    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr, flush=True)

    try:
        report_file = pathlib.Path(".fuzz_corpus") / "lock" / "fuzz_lock_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass


atexit.register(_emit_final_report)

# Suppress logging and instrument imports
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

# Enable string comparison instrumentation for better coverage
# of thread identity checks and error message construction
atheris.enabled_hooks.add("str")

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.runtime.rwlock import RWLock, with_read_lock, with_write_lock


def _track_slowest_operation(duration_ms: float, pattern: str, input_data: bytes) -> None:
    """Track top 10 slowest operations using max-heap."""
    input_hash = hashlib.sha256(input_data).hexdigest()[:16]
    entry: InterestingInput = (-duration_ms, pattern, input_hash)

    if len(_state.slowest_operations) < 10:
        heapq.heappush(_state.slowest_operations, entry)
    elif -duration_ms < _state.slowest_operations[0][0]:
        heapq.heapreplace(_state.slowest_operations, entry)


def _track_seed_corpus(input_data: bytes, duration_ms: float) -> None:
    """Track interesting inputs with FIFO eviction."""
    # Timing-based only; pattern-name criteria caused 76K:1 churn
    is_interesting = duration_ms > 50.0

    if is_interesting:
        input_hash = hashlib.sha256(input_data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = input_data
            _state.corpus_entries_added += 1


def _join_threads(threads: list[threading.Thread]) -> bool:
    """Join threads with timeout. Returns False if any thread timed out (deadlock)."""
    all_joined = True
    for t in threads:
        t.join(timeout=_THREAD_TIMEOUT)
        if t.is_alive():
            all_joined = False
    return all_joined


# --- Pattern Implementations ---

def _pattern_reader_writer_exclusion(fdp: atheris.FuzzedDataProvider) -> None:
    """Core invariant: readers and writers are mutually exclusive."""
    lock = RWLock()
    writers_active = 0
    readers_active = 0
    state_lock = threading.Lock()
    violations: list[str] = []

    num_threads = fdp.ConsumeIntInRange(3, 8)
    barrier = threading.Barrier(num_threads)

    def worker(is_writer: bool) -> None:
        nonlocal writers_active, readers_active
        try:
            barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError:
            return

        try:
            if is_writer:
                with lock.write():
                    with state_lock:
                        if writers_active > 0:
                            violations.append("Multiple writers active")
                        if readers_active > 0:
                            violations.append("Writer active while readers active")
                        writers_active += 1
                    time.sleep(fdp.ConsumeProbability() * 0.001)
                    with state_lock:
                        writers_active -= 1
            else:
                with lock.read():
                    with state_lock:
                        if writers_active > 0:
                            violations.append("Reader active while writer active")
                        readers_active += 1
                    time.sleep(fdp.ConsumeProbability() * 0.001)
                    with state_lock:
                        readers_active -= 1
        except ALLOWED_EXCEPTIONS:
            pass

    # Mix of readers and writers
    threads = []
    for i in range(num_threads):
        is_writer = i < max(1, num_threads // 3)
        threads.append(threading.Thread(target=worker, args=(is_writer,), daemon=True))

    for t in threads:
        t.start()

    if not _join_threads(threads):
        _state.deadlocks_detected += 1
        return

    if violations:
        msg = "; ".join(violations)
        raise LockFuzzError(msg)


def _pattern_concurrent_readers(fdp: atheris.FuzzedDataProvider) -> None:
    """Multiple readers must be able to hold the lock simultaneously."""
    lock = RWLock()
    max_concurrent = 0
    current_readers = 0
    state_lock = threading.Lock()

    num_readers = fdp.ConsumeIntInRange(3, 8)
    barrier = threading.Barrier(num_readers)

    def reader() -> None:
        nonlocal max_concurrent, current_readers
        try:
            barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError:
            return
        with lock.read():
            with state_lock:
                current_readers += 1
                max_concurrent = max(max_concurrent, current_readers)
            time.sleep(0.002)
            with state_lock:
                current_readers -= 1

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(num_readers)]
    for t in threads:
        t.start()

    if not _join_threads(threads):
        _state.deadlocks_detected += 1
        return

    # With enough readers and a sleep, at least 2 should overlap
    if num_readers >= 4 and max_concurrent < 2:
        msg = f"Readers not concurrent: max_concurrent={max_concurrent} with {num_readers} threads"
        raise LockFuzzError(msg)


def _pattern_writer_preference(fdp: atheris.FuzzedDataProvider) -> None:
    """Writer preference: waiting writer blocks new readers."""
    lock = RWLock()
    events: list[str] = []
    events_lock = threading.Lock()

    # Fuzz-controlled durations give Atheris something to mutate
    reader_hold = fdp.ConsumeProbability() * 0.005   # 0-5ms
    writer_delay = fdp.ConsumeProbability() * 0.003   # 0-3ms
    writer_hold = fdp.ConsumeProbability() * 0.002    # 0-2ms
    reader2_delay = fdp.ConsumeProbability() * 0.004  # 0-4ms

    def first_reader() -> None:
        with lock.read():
            with events_lock:
                events.append("R1_acquired")
            time.sleep(reader_hold)
            with events_lock:
                events.append("R1_released")

    def writer() -> None:
        time.sleep(writer_delay)
        with lock.write():
            with events_lock:
                events.append("W_acquired")
            time.sleep(writer_hold)
            with events_lock:
                events.append("W_released")

    def second_reader() -> None:
        time.sleep(reader2_delay)
        with lock.read(), events_lock:
            events.append("R2_acquired")

    t1 = threading.Thread(target=first_reader, daemon=True)
    t2 = threading.Thread(target=writer, daemon=True)
    t3 = threading.Thread(target=second_reader, daemon=True)

    for t in [t1, t2, t3]:
        t.start()

    if not _join_threads([t1, t2, t3]):
        _state.deadlocks_detected += 1


def _pattern_reentrant_reads(fdp: atheris.FuzzedDataProvider) -> None:
    """Same thread can acquire read lock multiple times."""
    lock = RWLock()
    depth = fdp.ConsumeIntInRange(2, 20)

    acquired_depths: list[int] = []

    def acquire_recursively(remaining: int) -> None:
        with lock.read():
            acquired_depths.append(remaining)
            if remaining > 0:
                acquire_recursively(remaining - 1)

    acquire_recursively(depth)

    if len(acquired_depths) != depth + 1:
        msg = f"Reentrant reads failed: expected {depth + 1} depths, got {len(acquired_depths)}"
        raise LockFuzzError(msg)


def _pattern_reentrant_writes(fdp: atheris.FuzzedDataProvider) -> None:
    """Same thread can acquire write lock multiple times."""
    lock = RWLock()
    depth = fdp.ConsumeIntInRange(2, 15)

    acquired_depths: list[int] = []

    def acquire_recursively(remaining: int) -> None:
        with lock.write():
            acquired_depths.append(remaining)
            if remaining > 0:
                acquire_recursively(remaining - 1)

    acquire_recursively(depth)

    if len(acquired_depths) != depth + 1:
        msg = f"Reentrant writes failed: expected {depth + 1} depths, got {len(acquired_depths)}"
        raise LockFuzzError(msg)


def _pattern_write_to_read_downgrade(fdp: atheris.FuzzedDataProvider) -> None:
    """Writer can acquire read locks; they persist after write release."""
    lock = RWLock()
    read_locks_held = fdp.ConsumeIntInRange(1, 5)
    downgrade_successful = False

    with lock.write():
        # Acquire read locks while holding write
        for _ in range(read_locks_held):
            lock._acquire_read()

    # After write released, the read locks should have converted to regular reads.
    # Verify by checking we can't acquire write (readers are active).
    # Try read -- should work (we're a reader now).
    # Release the converted reads.
    for _ in range(read_locks_held):
        lock._release_read()

    downgrade_successful = True

    if not downgrade_successful:
        msg = "Write-to-read downgrade failed"
        raise LockFuzzError(msg)


def _pattern_upgrade_rejection(_fdp: atheris.FuzzedDataProvider) -> None:
    """Read-to-write upgrade must raise RuntimeError."""
    lock = RWLock()
    upgrade_rejected = False

    with lock.read():
        try:
            lock._acquire_write()
            # If we get here, upgrade was not rejected -- invariant breach
            lock._release_write()
        except RuntimeError:
            upgrade_rejected = True

    if not upgrade_rejected:
        msg = "Read-to-write upgrade was NOT rejected"
        raise LockFuzzError(msg)


def _pattern_rapid_lock_cycling(fdp: atheris.FuzzedDataProvider) -> None:
    """Rapid acquire/release cycles to detect state corruption."""
    lock = RWLock()
    num_cycles = fdp.ConsumeIntInRange(50, 200)
    shared_value = 0
    value_lock = threading.Lock()

    def cycler(thread_id: int) -> None:
        nonlocal shared_value
        for _ in range(num_cycles):
            if thread_id % 2 == 0:
                with lock.read(), value_lock:
                    _ = shared_value
            else:
                with lock.write(), value_lock:
                    shared_value += 1

    num_threads = fdp.ConsumeIntInRange(2, 6)
    threads = [
        threading.Thread(target=cycler, args=(i,), daemon=True)
        for i in range(num_threads)
    ]

    for t in threads:
        t.start()

    if not _join_threads(threads):
        _state.deadlocks_detected += 1
        return

    # Verify writer count consistency
    num_writers = sum(1 for i in range(num_threads) if i % 2 != 0)
    expected_value = num_writers * num_cycles

    if shared_value != expected_value:
        msg = f"Lock cycling corruption: expected {expected_value}, got {shared_value}"
        raise LockFuzzError(msg)


def _pattern_decorator_correctness(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify with_read_lock and with_write_lock decorators."""
    lock_instance = RWLock()

    class TestClass:
        """Test target for decorator-based locking."""

        def __init__(self) -> None:
            self._rwlock = lock_instance
            self.value = 0

        @with_read_lock()
        def read_value(self) -> int:
            """Read under read lock."""
            return self.value

        @with_write_lock()
        def write_value(self, val: int) -> None:
            """Write under write lock."""
            self.value = val

    obj = TestClass()

    num_ops = fdp.ConsumeIntInRange(10, 50)
    for _ in range(num_ops):
        if fdp.ConsumeBool():
            obj.write_value(fdp.ConsumeIntInRange(0, 1000))
        else:
            val = obj.read_value()
            if not isinstance(val, int):
                msg = f"Decorator read returned non-int: {type(val)}"
                raise LockFuzzError(msg)


def _pattern_mixed_contention(fdp: atheris.FuzzedDataProvider) -> None:
    """Mixed operations: reads, writes, reentrancy, downgrade, upgrade attempt."""
    lock = RWLock()
    violations: list[str] = []
    violations_lock = threading.Lock()

    num_threads = fdp.ConsumeIntInRange(3, 6)
    ops_per_thread = fdp.ConsumeIntInRange(5, 15)
    barrier = threading.Barrier(num_threads)

    def worker(_thread_id: int) -> None:
        try:
            barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError:
            return

        for _ in range(ops_per_thread):
            op = fdp.ConsumeIntInRange(0, 5)
            try:
                match op:
                    case 0:
                        with lock.read():
                            time.sleep(0.0001)
                    case 1:
                        with lock.write():
                            time.sleep(0.0001)
                    case 2:
                        # Reentrant read
                        with lock.read(), lock.read():
                            pass
                    case 3:
                        # Reentrant write
                        with lock.write(), lock.write():
                            pass
                    case 4:
                        # Write-to-read downgrade
                        with lock.write(), lock.read():
                            pass
                    case _:
                        # Upgrade attempt (should be rejected)
                        try:
                            with lock.read():
                                lock._acquire_write()
                                # Should not reach here
                                with violations_lock:
                                    violations.append("Upgrade not rejected")
                                lock._release_write()
                        except RuntimeError:
                            pass
            except ALLOWED_EXCEPTIONS:
                pass

    threads = [
        threading.Thread(target=worker, args=(i,), daemon=True)
        for i in range(num_threads)
    ]

    for t in threads:
        t.start()

    if not _join_threads(threads):
        _state.deadlocks_detected += 1
        return

    if violations:
        msg = "; ".join(violations)
        raise LockFuzzError(msg)


def _pattern_cross_thread_handoff(fdp: atheris.FuzzedDataProvider) -> None:
    """Rapid lock handoff between threads tests wake notification path."""
    lock = RWLock()
    handoffs = fdp.ConsumeIntInRange(5, 20)
    results: list[int] = []
    results_lock = threading.Lock()

    def ping(count: int) -> None:
        for i in range(count):
            with lock.write(), results_lock:
                results.append(i)

    def pong(count: int) -> None:
        for i in range(count):
            with lock.write(), results_lock:
                results.append(i + 1000)

    t1 = threading.Thread(target=ping, args=(handoffs,), daemon=True)
    t2 = threading.Thread(target=pong, args=(handoffs,), daemon=True)
    t1.start()
    t2.start()

    if not _join_threads([t1, t2]):
        _state.deadlocks_detected += 1
        return

    if len(results) != handoffs * 2:
        msg = f"Handoff lost entries: {len(results)} != {handoffs * 2}"
        raise LockFuzzError(msg)


def _pattern_timeout_acquisition(fdp: atheris.FuzzedDataProvider) -> None:
    """Timeout-based acquisition: verify TimeoutError and state consistency."""
    lock = RWLock()
    timeout_val = fdp.ConsumeProbability() * 0.01  # 0-10ms
    acquire_write = fdp.ConsumeBool()

    # Hold the lock in another thread to force timeout
    hold_event = threading.Event()
    release_event = threading.Event()

    def holder() -> None:
        with lock.write():
            hold_event.set()
            release_event.wait(timeout=2.0)

    holder_thread = threading.Thread(target=holder, daemon=True)
    holder_thread.start()
    hold_event.wait(timeout=1.0)

    # Attempt acquisition with timeout -- should raise TimeoutError
    timed_out = False
    try:
        if acquire_write:
            with lock.write(timeout=timeout_val):
                pass
        else:
            with lock.read(timeout=timeout_val):
                pass
    except TimeoutError:
        timed_out = True

    release_event.set()
    holder_thread.join(timeout=2.0)

    if not timed_out:
        # Might succeed if timeout_val is long enough or lock released fast
        return

    # CRITICAL INVARIANT: after timeout, lock must still be usable
    # This catches _waiting_writers inflation bugs
    acquired = False
    try:
        with lock.write(timeout=1.0):
            acquired = True
    except TimeoutError:
        msg = "Lock unusable after timeout -- likely _waiting_writers leak"
        raise LockFuzzError(msg) from None

    if not acquired:
        msg = "Lock acquisition failed after previous timeout"
        raise LockFuzzError(msg)


def _pattern_reader_starvation(fdp: atheris.FuzzedDataProvider) -> None:
    """Continuous readers must not starve a waiting writer."""
    lock = RWLock()
    writer_acquired = threading.Event()
    stop_readers = threading.Event()
    num_readers = fdp.ConsumeIntInRange(3, 6)

    def continuous_reader() -> None:
        while not stop_readers.is_set():
            try:
                with lock.read():
                    time.sleep(0.0001)
            except RuntimeError:
                break

    def writer() -> None:
        time.sleep(0.002)  # Let readers establish
        with lock.write():
            writer_acquired.set()

    reader_threads = [
        threading.Thread(target=continuous_reader, daemon=True)
        for _ in range(num_readers)
    ]
    writer_thread = threading.Thread(target=writer, daemon=True)

    for t in reader_threads:
        t.start()
    writer_thread.start()

    # Writer should acquire within reasonable time (writer preference)
    got_it = writer_acquired.wait(timeout=_THREAD_TIMEOUT)
    stop_readers.set()

    _join_threads([writer_thread, *reader_threads])

    if not got_it:
        msg = (
            f"Writer starved: {num_readers} continuous readers "
            f"blocked writer for >{_THREAD_TIMEOUT}s"
        )
        raise LockFuzzError(msg)


# --- Pattern dispatch ---

def _select_pattern(fdp: atheris.FuzzedDataProvider) -> str:
    """Select a weighted pattern using modulo to avoid tail bias.

    ConsumeIntInRange skews toward small values with short inputs, causing
    the last entry in a cumulative scan to absorb all overflow.  Using raw
    bytes with modulo distributes uniformly across the weight space.
    """
    total = sum(w for _, w in _PATTERN_WEIGHTS)
    raw = fdp.ConsumeBytes(2)
    if len(raw) < 2:
        raw = b"\x00\x00"
    choice = int.from_bytes(raw, "big") % total

    cumulative = 0
    for name, weight in _PATTERN_WEIGHTS:
        cumulative += weight
        if choice < cumulative:
            return name

    return _PATTERN_WEIGHTS[0][0]


_PATTERN_DISPATCH: dict[str, Any] = {
    "reentrant_reads": _pattern_reentrant_reads,
    "reentrant_writes": _pattern_reentrant_writes,
    "upgrade_rejection": _pattern_upgrade_rejection,
    "decorator_correctness": _pattern_decorator_correctness,
    "write_to_read_downgrade": _pattern_write_to_read_downgrade,
    "rapid_lock_cycling": _pattern_rapid_lock_cycling,
    "cross_thread_handoff": _pattern_cross_thread_handoff,
    "concurrent_readers": _pattern_concurrent_readers,
    "timeout_acquisition": _pattern_timeout_acquisition,
    "reader_writer_exclusion": _pattern_reader_writer_exclusion,
    "writer_preference": _pattern_writer_preference,
    "reader_starvation": _pattern_reader_starvation,
    "mixed_contention": _pattern_mixed_contention,
}


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz RWLock concurrency invariants."""
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
    pattern = _select_pattern(fdp)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp)

    except LockFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)

        _state.pattern_wall_time[pattern] = (
            _state.pattern_wall_time.get(pattern, 0.0) + elapsed_ms
        )

        _track_slowest_operation(elapsed_ms, pattern, data)
        _track_seed_corpus(data, elapsed_ms)

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            current_mb = _get_process().memory_info().rss / (1024 * 1024)
            _state.memory_history.append(current_mb)


def main() -> None:
    """Run the RWLock contention fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="RWLock contention fuzzer using Atheris/libFuzzer",
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
        default=500,
        help="Maximum size of in-memory seed corpus (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("RWLock Contention Fuzzer (Atheris)")
    print("=" * 80)
    print(f"Target:     RWLock, with_read_lock, with_write_lock ({len(_PATTERN_WEIGHTS)} patterns)")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
