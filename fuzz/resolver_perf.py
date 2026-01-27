#!/usr/bin/env python3
"""Resolver Performance Fuzzer (Atheris).

Targets: ftllexengine.runtime.bundle.FluentBundle.format_value
Detects algorithmic complexity attacks in the resolver (deeply chained refs).
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import sys
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
    from ftllexengine.runtime.bundle import FluentBundle

class ResolverPerfError(Exception):
    """Raised when resolution exceeds time limits."""

THRESHOLD_MS = int(os.environ.get("FUZZ_RESOLVER_THRESHOLD_MS", "50"))

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Detect algorithmic complexity attacks in resolver."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # Strat: Generate long chain of references: msg1 = { msg2 }, msg2 = { msg3 } ...
    chain_len = fdp.ConsumeIntInRange(1, 100)
    ftl = []
    for i in range(chain_len):
        if i == chain_len - 1:
            ftl.append(f"msg{i} = Final")
        else:
            ftl.append(f"msg{i} = {{ msg{i+1} }}")

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource("\n".join(ftl))

    start = time.perf_counter()
    try:
        _, _ = bundle.format_value("msg0")
    except Exception:
        # Unexpected crash during perf fuzzing is a finding
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise
    duration_ms = (time.perf_counter() - start) * 1000

    # Invariant: Performance must be stable
    if duration_ms > THRESHOLD_MS:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        msg = f"Slow resolution: {duration_ms:.2f}ms (threshold: {THRESHOLD_MS}ms)"
        raise ResolverPerfError(msg)

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
