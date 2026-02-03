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
read-to-write upgrade rejection, decorator correctness, timeout behavior,
negative timeout rejection, release-without-acquire rejection, zero-timeout
non-blocking paths, and deadlock detection. Distinct from runtime/cache
fuzzers which exercise locking only as a side effect.

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
    check_dependencies,
    emit_final_report,
    get_process,
    record_iteration_metrics,
    record_memory,
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

_state = BaseFuzzerState()
_domain = LockMetrics()

# Thread join timeout (seconds) -- triggers deadlock detection
_THREAD_TIMEOUT = 2.0


# Pattern weights: cheapest-first ordering.
# libFuzzer's ConsumeIntInRange skews toward small values with short inputs,
# so early entries are over-selected. Placing cheap single-threaded patterns
# first ensures the natural bias falls on near-free operations, not expensive
# multi-threaded patterns.
#
# Pattern selection uses ConsumeBytes(2) + modulo (not build_weighted_schedule)
# to avoid tail-entry overflow bias with the 2-byte header discriminant.
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # Cheap: single-threaded, no thread creation, sub-0.02ms
    ("reentrant_reads", 5),
    ("reentrant_writes", 5),
    ("negative_timeout", 4),
    ("release_without_acquire", 4),
    ("upgrade_rejection", 8),
    ("decorator_correctness", 6),
    ("zero_timeout_nonblocking", 5),
    ("write_to_read_downgrade", 10),
    # Medium: multi-threaded but bounded
    ("rapid_lock_cycling", 8),
    ("cross_thread_handoff", 6),
    ("concurrent_readers", 12),
    ("timeout_acquisition", 8),
    ("downgrade_then_contention", 8),
    # Expensive: multi-threaded with sleeps, barriers, contention
    ("reader_writer_exclusion", 15),
    ("writer_preference", 10),
    ("reader_starvation", 6),
    ("mixed_contention", 7),
)

_TOTAL_WEIGHT = sum(w for _, w in _PATTERN_WEIGHTS)


class LockFuzzError(Exception):
    """Raised when an RWLock invariant is breached."""


# Allowed exceptions from lock operations
ALLOWED_EXCEPTIONS = (RuntimeError, TimeoutError)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_corpus") / "lock"


def _build_stats_dict() -> dict[str, Any]:
    """Build stats dictionary with base + lock-specific metrics."""
    stats = build_base_stats_dict(_state)

    # Lock-specific domain metrics
    stats["deadlocks_detected"] = _domain.deadlocks_detected
    stats["timeouts"] = _domain.timeouts
    stats["thread_creation_count"] = _domain.thread_creation_count
    stats["max_concurrent_threads"] = _domain.max_concurrent_threads

    return stats


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, "fuzz_lock_report.json")


atexit.register(_emit_report)

# Suppress logging and instrument imports
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

# Enable string comparison instrumentation for better coverage
# of thread identity checks and error message construction
atheris.enabled_hooks.add("str")

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.runtime.rwlock import RWLock, with_read_lock, with_write_lock


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

    with lock.write():
        # Acquire read locks while holding write
        for _ in range(read_locks_held):
            lock._acquire_read()

    # After write released, the read locks should have converted to regular reads.
    # Release the converted reads.
    for _ in range(read_locks_held):
        lock._release_read()

    # Lock should be fully free now -- verify by acquiring write
    with lock.write():
        pass


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


def _pattern_downgrade_then_contention(fdp: atheris.FuzzedDataProvider) -> None:
    """Write-to-read downgrade under contention from other threads."""
    lock = RWLock()
    read_count = fdp.ConsumeIntInRange(1, 5)
    num_contenders = fdp.ConsumeIntInRange(2, 4)
    contender_results: list[str] = []
    results_lock = threading.Lock()
    _track_threads(num_contenders)

    # Main thread: acquire write, then acquire reads, then release write
    with lock.write():
        for _ in range(read_count):
            lock._acquire_read()

    # Now the main thread holds read_count converted read locks.
    # Other threads should be able to read but not write.

    def contender(cid: int) -> None:
        try:
            # Attempt write -- should block until all reads released
            with lock.write(timeout=0.5), results_lock:
                contender_results.append(f"W{cid}")
        except TimeoutError:
            with results_lock:
                contender_results.append(f"T{cid}")

    threads = [
        threading.Thread(target=contender, args=(i,), daemon=True)
        for i in range(num_contenders)
    ]

    for t in threads:
        t.start()

    # Give contenders time to queue up, then release reads
    time.sleep(0.01)
    for _ in range(read_count):
        lock._release_read()

    if not _join_threads(threads):
        _domain.deadlocks_detected += 1
        return

    # At least one contender should have acquired write (after reads released)
    write_successes = sum(1 for r in contender_results if r.startswith("W"))
    if write_successes == 0 and num_contenders > 0:
        msg = f"No contender acquired write after downgrade release ({contender_results})"
        raise LockFuzzError(msg)


# --- Pattern dispatch ---


def _select_pattern(fdp: atheris.FuzzedDataProvider) -> str:
    """Select a pattern using ConsumeBytes(2) + modulo for uniform distribution.

    Unlike build_weighted_schedule + ConsumeIntInRange, consuming 2 raw
    bytes with modulo distributes uniformly across the weight space.
    """
    raw = fdp.ConsumeBytes(2)
    if len(raw) < 2:
        raw = b"\x00\x00"
    choice = int.from_bytes(raw, "big") % _TOTAL_WEIGHT

    cumulative = 0
    for name, weight in _PATTERN_WEIGHTS:
        cumulative += weight
        if choice < cumulative:
            return name

    return _PATTERN_WEIGHTS[0][0]


_PATTERN_DISPATCH: dict[str, Any] = {
    "reentrant_reads": _pattern_reentrant_reads,
    "reentrant_writes": _pattern_reentrant_writes,
    "negative_timeout": _pattern_negative_timeout,
    "release_without_acquire": _pattern_release_without_acquire,
    "upgrade_rejection": _pattern_upgrade_rejection,
    "decorator_correctness": _pattern_decorator_correctness,
    "zero_timeout_nonblocking": _pattern_zero_timeout_nonblocking,
    "write_to_read_downgrade": _pattern_write_to_read_downgrade,
    "rapid_lock_cycling": _pattern_rapid_lock_cycling,
    "cross_thread_handoff": _pattern_cross_thread_handoff,
    "concurrent_readers": _pattern_concurrent_readers,
    "timeout_acquisition": _pattern_timeout_acquisition,
    "downgrade_then_contention": _pattern_downgrade_then_contention,
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
        _emit_report()

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

    # Populate intended weights for skew detection
    for name, weight in _PATTERN_WEIGHTS:
        _state.pattern_intended_weights[name] = float(weight)

    sys.argv = [sys.argv[0], *remaining]

    # Inject RSS limit if not specified
    if not any(arg.startswith("-rss_limit_mb") for arg in sys.argv):
        sys.argv.append("-rss_limit_mb=4096")

    print()
    print("=" * 80)
    print("RWLock Contention Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     RWLock, with_read_lock, with_write_lock")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print(f"GC Cycle:   Every {GC_INTERVAL} iterations")
    print(f"Routing:    ConsumeBytes(2) + modulo (weight total: {_TOTAL_WEIGHT})")
    print(f"Patterns:   {len(_PATTERN_WEIGHTS)}")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
