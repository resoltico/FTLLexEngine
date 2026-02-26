#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: lock - RWLock Concurrency & Contention
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""RWLock Contention Fuzzer (Atheris).

Targets: ftllexengine.runtime.rwlock.RWLock

Concern boundary: This fuzzer stress-tests the RWLock concurrency primitive
directly. Tests reader/writer mutual exclusion, reader concurrency, writer
preference, reentrant readers, read-to-write upgrade rejection,
write-to-write reentry rejection, write-to-read downgrade rejection,
timeout behavior, negative timeout rejection, release-without-acquire
rejection, zero-timeout non-blocking paths, and deadlock detection.
Distinct from runtime/cache fuzzers which exercise locking only as a side effect.

Metrics:
- Pattern coverage (reader_writer_exclusion, reentrant_reads, etc.)
- Weight skew detection (actual vs intended distribution)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Corpus retention rate and eviction tracking
- Thread contention events and deadlock detection
- Seed corpus management

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import logging
import pathlib
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

# --- Dependency Checks ---
_psutil_mod: Any = None
_atheris_mod: Any = None

try:  # noqa: SIM105 - need module ref for check_dependencies
    import psutil as _psutil_mod  # type: ignore[no-redef]
except ImportError:
    pass

try:  # noqa: SIM105 - need module ref for check_dependencies
    import atheris as _atheris_mod  # type: ignore[no-redef]
except ImportError:
    pass

from fuzz_common import (  # noqa: E402 - after dependency capture  # pylint: disable=C0413
    GC_INTERVAL,
    BaseFuzzerState,
    build_base_stats_dict,
    build_weighted_schedule,
    check_dependencies,
    emit_checkpoint_report,
    emit_final_report,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---

@dataclass
class LockMetrics:
    """Domain-specific metrics for lock contention fuzzer."""

    deadlocks_detected: int = 0
    timeouts: int = 0
    thread_creation_count: int = 0
    max_concurrent_threads: int = 0


# --- Global State ---

_state = BaseFuzzerState(
    fuzzer_name="lock",
    fuzzer_target="RWLock concurrency",
)
_domain = LockMetrics()

# Thread join timeout (seconds) -- triggers deadlock detection
_THREAD_TIMEOUT = 2.0


# Pattern weights: cheapest-first ordering.
# libFuzzer's ConsumeIntInRange skews toward small values with short inputs,
# so early entries are over-selected. Placing cheap single-threaded patterns
# first ensures the natural bias falls on near-free operations, not expensive
# multi-threaded patterns.
#
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # Cheap: single-threaded, no thread creation, sub-0.02ms
    ("reentrant_reads", 5),
    ("write_reentry_rejection", 4),
    ("downgrade_rejection", 4),
    ("negative_timeout", 4),
    ("release_without_acquire", 4),
    ("upgrade_rejection", 8),
    ("zero_timeout_nonblocking", 5),
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

_PATTERN_NAMES = tuple(name for name, _ in _PATTERN_WEIGHTS)
_PATTERN_WEIGHT_VALUES = tuple(w for _, w in _PATTERN_WEIGHTS)
_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(_PATTERN_NAMES, _PATTERN_WEIGHT_VALUES)

# Register intended weights for skew detection (module-level, not in main())
for _name, _weight in _PATTERN_WEIGHTS:
    _state.pattern_intended_weights[_name] = float(_weight)


class LockFuzzError(Exception):
    """Raised when an RWLock invariant is breached."""


# Allowed exceptions from lock operations
ALLOWED_EXCEPTIONS = (RuntimeError, TimeoutError)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "lock"


def _build_stats_dict() -> dict[str, Any]:
    """Build stats dictionary with base + lock-specific metrics."""
    stats = build_base_stats_dict(_state)

    # Lock-specific domain metrics
    stats["deadlocks_detected"] = _domain.deadlocks_detected
    stats["timeouts"] = _domain.timeouts
    stats["thread_creation_count"] = _domain.thread_creation_count
    stats["max_concurrent_threads"] = _domain.max_concurrent_threads

    return stats


_REPORT_FILENAME = "fuzz_lock_report.json"


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(
        _state, stats, _REPORT_DIR, _REPORT_FILENAME,
    )


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)

# Suppress logging and instrument imports
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

# Enable string comparison instrumentation for better coverage
# of thread identity checks and error message construction
atheris.enabled_hooks.add("str")

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.runtime.rwlock import RWLock


def _join_threads(threads: list[threading.Thread]) -> bool:
    """Join threads with timeout. Returns False if any thread timed out (deadlock)."""
    all_joined = True
    for t in threads:
        t.join(timeout=_THREAD_TIMEOUT)
        if t.is_alive():
            all_joined = False
    return all_joined


def _track_threads(count: int) -> None:
    """Track thread creation for domain metrics."""
    _domain.thread_creation_count += count
    _domain.max_concurrent_threads = max(_domain.max_concurrent_threads, count)


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
    _track_threads(num_threads)

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
        _domain.deadlocks_detected += 1
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
    _track_threads(num_readers)

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
        _domain.deadlocks_detected += 1
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
    _track_threads(3)

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
        _domain.deadlocks_detected += 1


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


def _pattern_write_reentry_rejection(_fdp: atheris.FuzzedDataProvider) -> None:
    """Write-to-write reentry must raise RuntimeError."""
    lock = RWLock()
    reentry_rejected = False

    with lock.write():
        try:
            lock._acquire_write()
            # If we get here, reentry was not rejected -- invariant breach
            lock._release_write()
        except RuntimeError:
            reentry_rejected = True

    if not reentry_rejected:
        msg = "Write-to-write reentry was NOT rejected"
        raise LockFuzzError(msg)


def _pattern_downgrade_rejection(_fdp: atheris.FuzzedDataProvider) -> None:
    """Write-to-read downgrade must raise RuntimeError."""
    lock = RWLock()
    downgrade_rejected = False

    with lock.write():
        try:
            lock._acquire_read()
            # If we get here, downgrade was not rejected -- invariant breach
            lock._release_read()
        except RuntimeError:
            downgrade_rejected = True

    if not downgrade_rejected:
        msg = "Write-to-read downgrade was NOT rejected"
        raise LockFuzzError(msg)


def _pattern_rapid_lock_cycling(fdp: atheris.FuzzedDataProvider) -> None:
    """Rapid acquire/release cycles to detect state corruption."""
    lock = RWLock()
    num_cycles = fdp.ConsumeIntInRange(50, 200)
    shared_value = 0
    value_lock = threading.Lock()

    num_threads = fdp.ConsumeIntInRange(2, 6)
    _track_threads(num_threads)

    def cycler(thread_id: int) -> None:
        nonlocal shared_value
        for _ in range(num_cycles):
            if thread_id % 2 == 0:
                with lock.read(), value_lock:
                    _ = shared_value
            else:
                with lock.write(), value_lock:
                    shared_value += 1

    threads = [
        threading.Thread(target=cycler, args=(i,), daemon=True)
        for i in range(num_threads)
    ]

    for t in threads:
        t.start()

    if not _join_threads(threads):
        _domain.deadlocks_detected += 1
        return

    # Verify writer count consistency
    num_writers = sum(1 for i in range(num_threads) if i % 2 != 0)
    expected_value = num_writers * num_cycles

    if shared_value != expected_value:
        msg = f"Lock cycling corruption: expected {expected_value}, got {shared_value}"
        raise LockFuzzError(msg)


def _pattern_mixed_contention(  # noqa: PLR0915 - 6 distinct op types; each prohibition case requires try/except + violation recording
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Mixed operations: reads, writes, reentrancy, prohibition checks, upgrade attempt."""
    lock = RWLock()
    violations: list[str] = []
    violations_lock = threading.Lock()

    num_threads = fdp.ConsumeIntInRange(3, 6)
    ops_per_thread = fdp.ConsumeIntInRange(5, 15)
    barrier = threading.Barrier(num_threads)
    _track_threads(num_threads)

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
                        # Reentrant read (permitted)
                        with lock.read(), lock.read():
                            pass
                    case 3:
                        # Write-to-write reentry must raise RuntimeError
                        with lock.write():
                            try:
                                lock._acquire_write()
                                lock._release_write()
                                with violations_lock:
                                    violations.append("Write reentry not rejected")
                            except RuntimeError:
                                pass
                    case 4:
                        # Write-to-read downgrade must raise RuntimeError
                        with lock.write():
                            try:
                                lock._acquire_read()
                                lock._release_read()
                                with violations_lock:
                                    violations.append("Downgrade not rejected")
                            except RuntimeError:
                                pass
                    case _:
                        # Read-to-write upgrade must raise RuntimeError
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
        _domain.deadlocks_detected += 1
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
    _track_threads(2)

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
        _domain.deadlocks_detected += 1
        return

    if len(results) != handoffs * 2:
        msg = f"Handoff lost entries: {len(results)} != {handoffs * 2}"
        raise LockFuzzError(msg)


def _pattern_timeout_acquisition(fdp: atheris.FuzzedDataProvider) -> None:
    """Timeout-based acquisition: verify TimeoutError and state consistency."""
    lock = RWLock()
    timeout_val = fdp.ConsumeProbability() * 0.01  # 0-10ms
    acquire_write = fdp.ConsumeBool()
    _track_threads(1)

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
        _domain.timeouts += 1

    release_event.set()
    holder_thread.join(timeout=2.0)

    if not timed_out:
        # Might succeed if timeout_val is long enough or lock released fast
        return

    # CRITICAL INVARIANT: after timeout, lock must still be usable.
    # This catches _waiting_writers inflation bugs.
    try:
        with lock.write(timeout=1.0):
            pass
    except TimeoutError:
        msg = "Lock unusable after timeout -- likely _waiting_writers leak"
        raise LockFuzzError(msg) from None


def _pattern_reader_starvation(fdp: atheris.FuzzedDataProvider) -> None:
    """Continuous readers must not starve a waiting writer."""
    lock = RWLock()
    writer_acquired = threading.Event()
    stop_readers = threading.Event()
    num_readers = fdp.ConsumeIntInRange(3, 6)
    _track_threads(num_readers + 1)

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


# --- New Patterns ---


def _pattern_negative_timeout(fdp: atheris.FuzzedDataProvider) -> None:
    """Negative timeout must raise ValueError before any state mutation."""
    lock = RWLock()
    # Fuzz the magnitude of the negative value
    magnitude = fdp.ConsumeProbability() * 100.0 + 0.001  # always > 0
    negative_val = -magnitude
    test_write = fdp.ConsumeBool()

    try:
        if test_write:
            with lock.write(timeout=negative_val):
                pass
        else:
            with lock.read(timeout=negative_val):
                pass
    except ValueError:
        # Expected -- verify lock is still usable
        with lock.write():
            pass
        return

    msg = f"Negative timeout ({negative_val}) did not raise ValueError"
    raise LockFuzzError(msg)


def _pattern_release_without_acquire(fdp: atheris.FuzzedDataProvider) -> None:
    """Releasing a lock not held by current thread must raise RuntimeError."""
    lock = RWLock()
    test_write = fdp.ConsumeBool()

    try:
        if test_write:
            lock._release_write()
        else:
            lock._release_read()
    except RuntimeError:
        # Expected -- verify lock is still usable
        with lock.write():
            pass
        return

    kind = "write" if test_write else "read"
    msg = f"Release {kind} without acquire did not raise RuntimeError"
    raise LockFuzzError(msg)


def _pattern_zero_timeout_nonblocking(fdp: atheris.FuzzedDataProvider) -> None:
    """Zero timeout must fail immediately when lock is held."""
    lock = RWLock()
    test_write_attempt = fdp.ConsumeBool()
    _track_threads(1)

    # Hold the lock in another thread
    hold_event = threading.Event()
    release_event = threading.Event()

    def holder() -> None:
        with lock.write():
            hold_event.set()
            release_event.wait(timeout=2.0)

    holder_thread = threading.Thread(target=holder, daemon=True)
    holder_thread.start()
    hold_event.wait(timeout=1.0)

    # Zero timeout should fail immediately
    timed_out = False
    start = time.perf_counter()
    try:
        if test_write_attempt:
            with lock.write(timeout=0.0):
                pass
        else:
            with lock.read(timeout=0.0):
                pass
    except TimeoutError:
        timed_out = True
        _domain.timeouts += 1

    elapsed_ms = (time.perf_counter() - start) * 1000

    release_event.set()
    holder_thread.join(timeout=2.0)

    if not timed_out:
        # Lock might have been released between hold_event.set() and our attempt
        return

    # Non-blocking attempt should return very quickly (< 50ms)
    if elapsed_ms > 50.0:
        msg = f"Zero-timeout took {elapsed_ms:.1f}ms (expected < 50ms)"
        raise LockFuzzError(msg)


# --- Pattern dispatch ---


_PATTERN_DISPATCH: dict[str, Any] = {
    "reentrant_reads": _pattern_reentrant_reads,
    "write_reentry_rejection": _pattern_write_reentry_rejection,
    "downgrade_rejection": _pattern_downgrade_rejection,
    "negative_timeout": _pattern_negative_timeout,
    "release_without_acquire": _pattern_release_without_acquire,
    "upgrade_rejection": _pattern_upgrade_rejection,
    "zero_timeout_nonblocking": _pattern_zero_timeout_nonblocking,
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
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp)

    except LockFuzzError:
        _state.findings += 1
        raise

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = (
            "timeout" in pattern
            or "contention" in pattern
            or (time.perf_counter() - start_time) * 1000 > 50.0
        )
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        # Break reference cycles from threading objects
        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            record_memory(_state)


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

    # Inject RSS limit if not specified
    if not any(arg.startswith("-rss_limit_mb") for arg in sys.argv):
        sys.argv.append("-rss_limit_mb=4096")

    print_fuzzer_banner(
        title="RWLock Contention Fuzzer (Atheris)",
        target="RWLock",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
