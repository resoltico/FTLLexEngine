#!/usr/bin/env python3
"""High-Pressure Cache Race Fuzzer (Atheris).

Targets: ftllexengine.runtime.cache.SimpleCache (via FluentBundle)
Stresses cache invalidation, key collision, and multi-threaded resolution synchronization.
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
import threading

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
    from ftllexengine.runtime.bundle import FluentBundle

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Stress-test cache under concurrent access."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Setup bundle with randomized cache size
    cache_size = fdp.ConsumeIntInRange(1, 20)
    bundle = FluentBundle("en-US", enable_cache=True, cache_size=cache_size)

    # Define some messages
    ftl = "".join([f"msg{i} = Value {i} {{ $var }}\n" for i in range(10)])
    bundle.add_resource(ftl)

    errors = []

    def worker():
        try:
            # Randomly pick a message and a variable
            m_idx = fdp.ConsumeIntInRange(0, 9)
            v_val = fdp.ConsumeUnicodeNoSurrogates(5)

            val, errs = bundle.format_value(f"msg{m_idx}", {"var": v_val})

            # Simple check: result should contain the variable
            if v_val not in val and not errs:
                errors.append(f"Inconsistent resolution: expected {v_val} in '{val}'")
        except Exception as e:  # pylint: disable=broad-exception-caught # Fuzzer: record thread crashes for race condition detection
            errors.append(f"Worker crashed: {e}")

    # 2. Spawn multiple threads to hit the cache simultaneously
    num_threads = fdp.ConsumeIntInRange(2, 8)
    threads = [threading.Thread(target=worker) for _ in range(num_threads)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if errors:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise RuntimeError("\n".join(errors))

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
