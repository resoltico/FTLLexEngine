#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: lock - RWLock Concurrency & Contention
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""RWLock Contention Fuzzer (Atheris).

Targets: ftllexengine.runtime.rwlock.RWLock
Tests concurrency, reentrancy, and deadlock prevention.

This fuzzer uses multiple threads to aggressively stress the lock's invariants.
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
import threading
import time

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str]

_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}

def _emit_final_report() -> None:
    report = json.dumps(_fuzz_stats)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)

atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    sys.exit(1)

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.runtime.rwlock import RWLock

class ConcurrencyError(Exception):
    """Raised when an RWLock invariant is breached."""

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Stress-test RWLock invariants under concurrent access."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    lock = RWLock()
    # Separate tracking for counts and error to maintain type safety
    writers_count = 0
    readers_count = 0
    error_msg: str | None = None
    state_lock = threading.Lock()

    def run_lock_op():
        nonlocal writers_count, readers_count, error_msg
        try:
            op_type = fdp.ConsumeIntInRange(0, 2)
            # 0 = Read, 1 = Write, 2 = Reentrant Read

            if op_type == 0:
                with lock.read():
                    with state_lock:
                        if writers_count > 0:
                            error_msg = "Reader acquired while Writer active"
                        readers_count += 1
                    # Small randomized delay
                    time.sleep(fdp.ConsumeProbability() * 0.005)
                    with state_lock:
                        readers_count -= 1
            elif op_type == 1:
                try:
                    with lock.write():
                        with state_lock:
                            if writers_count > 0:
                                error_msg = "Multiple Writers active"
                            if readers_count > 0:
                                error_msg = "Writer active while Readers active"
                            writers_count += 1
                        time.sleep(fdp.ConsumeProbability() * 0.005)
                        with state_lock:
                            writers_count -= 1
                except RuntimeError as e:
                    if "upgrade" not in str(e).lower():
                        raise
            else:
                # Test reentrancy
                with lock.read(), lock.read():
                    pass
        except Exception as e:  # pylint: disable=broad-exception-caught # Fuzzer: record lock crashes for deadlock/race detection
            with state_lock:
                error_msg = f"CRASH: {type(e).__name__}: {e}"

    # Spawn threads
    num_threads = fdp.ConsumeIntInRange(2, 10)
    threads = [threading.Thread(target=run_lock_op) for _ in range(num_threads)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if error_msg:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise ConcurrencyError(error_msg)

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
