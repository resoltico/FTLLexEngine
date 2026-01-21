#!/usr/bin/env python3
"""Performance Fuzzer (Atheris).

Detects algorithmic complexity attacks (ReDoS, quadratic behavior).
Measures parse time and flags inputs that exceed size-scaled thresholds.

Built for Python 3.13+ using modern PEPs (695, 585, 563).
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import time

# --- PEP 695 Type Aliases (Python 3.13) ---
type FuzzStats = dict[str, int | str]

# Crash-proof reporting: ensure summary is always emitted
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}


def _emit_final_report() -> None:
    """Emit JSON summary on exit (crash-proof reporting)."""
    report = json.dumps(_fuzz_stats)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)


atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    print("-" * 80, file=sys.stderr)
    print("ERROR: 'atheris' not found.", file=sys.stderr)
    print("On macOS, install LLVM: brew install llvm", file=sys.stderr)
    print("Then set: export CC=$(brew --prefix llvm)/bin/clang", file=sys.stderr)
    print("And reinstall: uv sync", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# Suppress parser logging during fuzzing (reduces I/O noise in timing measurements)
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.parser import FluentParserV1


class PerformanceBreachError(Exception):
    """Raised when parsing exceeds the calculated time threshold."""


# Threshold model accounting for Atheris ~30-50x instrumentation overhead
# Configurable via environment variables for different hardware profiles
THRESHOLD_BASE_MS = int(os.environ.get("FUZZ_PERF_BASE_MS", "100"))
THRESHOLD_SCALE_MS_PER_KB = int(os.environ.get("FUZZ_PERF_SCALE_MS_KB", "20"))
MAX_INPUT_SIZE = int(os.environ.get("FUZZ_PERF_MAX_SIZE", "50000"))


def _compute_threshold(input_size: int) -> float:
    """Compute size-scaled threshold in seconds.

    Atheris coverage instrumentation adds ~30-50x overhead.
    Threshold = base_ms + scale_ms per KB.
    """
    size_kb = input_size / 1000
    threshold_ms = THRESHOLD_BASE_MS + (THRESHOLD_SCALE_MS_PER_KB * size_kb)
    return threshold_ms / 1000


def test_one_input(data: bytes) -> None:
    """Atheris entry point: parse fuzzed input and measure time."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    try:
        source = fdp.ConsumeUnicodeNoSurrogates(MAX_INPUT_SIZE)
    except (UnicodeDecodeError, ValueError):
        source = data.decode("utf-8", errors="replace")[:MAX_INPUT_SIZE]

    parser = FluentParserV1()

    start = time.perf_counter()
    try:
        parser.parse(source)
    except (ValueError, RecursionError, MemoryError):
        pass  # Expected for invalid input
    except Exception as e:
        # Unexpected crash during performance fuzzing is also a finding
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        _fuzz_stats["status"] = "finding"
        print(f"\n[CRASH] {type(e).__name__}: {e}")
        raise
    duration = time.perf_counter() - start

    threshold = _compute_threshold(len(source))
    if duration > threshold:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        _fuzz_stats["status"] = "finding"
        ratio = duration / threshold

        print()
        print("=" * 80)
        print("[FINDING] PERFORMANCE BREACH DETECTED")
        print("=" * 80)
        print(f"Duration:   {duration:.4f}s (threshold: {threshold:.4f}s)")
        print(f"Input size: {len(source)} characters")
        print(f"Ratio:      {ratio:.2f}x threshold")
        print("-" * 80)
        print("NEXT STEPS:")
        print("  1. Review slow input: xxd .fuzz_corpus/crash_* | head -20")
        print("  2. Create performance test in tests/")
        print("  3. Profile and fix the algorithm")
        print("=" * 80)

        msg = f"Complexity spike: {duration:.4f}s ({ratio:.2f}x threshold)"
        raise PerformanceBreachError(msg)


def main() -> None:
    """Run the performance fuzzer."""
    print()
    print("=" * 80)
    print("Fluent Performance Fuzzer (Python 3.13 Edition)")
    print("=" * 80)
    print("Target:   ReDoS and algorithmic complexity detection")
    print(f"Config:   {THRESHOLD_BASE_MS}ms base + {THRESHOLD_SCALE_MS_PER_KB}ms/KB")
    print("Stopping: Press Ctrl+C at any time (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
