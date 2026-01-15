#!/usr/bin/env python3
"""Performance Fuzzer (Atheris).

Detects algorithmic complexity attacks (ReDoS, quadratic behavior).
Measures parse time and flags inputs that exceed size-scaled thresholds.

Usage:
    ./scripts/fuzz-atheris.sh 4 fuzz/perf.py
    ./scripts/fuzz-atheris.sh 4 fuzz/perf.py -max_total_time=60

Environment Variables (for threshold tuning):
    FUZZ_PERF_BASE_MS       Base threshold in ms (default: 100)
    FUZZ_PERF_SCALE_MS_KB   Additional ms per KB of input (default: 20)
    FUZZ_PERF_MAX_SIZE      Max input size in chars (default: 50000)

Example:
    # Stricter thresholds for fast machines
    FUZZ_PERF_BASE_MS=50 FUZZ_PERF_SCALE_MS_KB=10 ./scripts/fuzz.sh --perf

    # Relaxed thresholds for slow machines or heavy instrumentation
    FUZZ_PERF_BASE_MS=200 FUZZ_PERF_SCALE_MS_KB=40 ./scripts/fuzz.sh --perf
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import time

# Crash-proof reporting: ensure summary is always emitted
_fuzz_stats: dict[str, int | str] = {"status": "incomplete", "iterations": 0, "findings": 0}


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

with atheris.instrument_imports():
    from ftllexengine.syntax.parser import FluentParserV1


class SlowParsing(Exception):  # noqa: N818 - Domain-specific name
    """Raised when parsing exceeds the time threshold."""


# Threshold model accounting for Atheris ~30-50x instrumentation overhead
# Configurable via environment variables for different hardware profiles
THRESHOLD_BASE_MS = int(os.environ.get("FUZZ_PERF_BASE_MS", "100"))
THRESHOLD_SCALE_MS_PER_KB = int(os.environ.get("FUZZ_PERF_SCALE_MS_KB", "20"))
MAX_INPUT_SIZE = int(os.environ.get("FUZZ_PERF_MAX_SIZE", "50000"))


def compute_threshold(input_size: int) -> float:
    """Compute size-scaled threshold in seconds.

    Atheris coverage instrumentation adds ~30-50x overhead.
    Threshold = 100ms + 20ms per KB.
    """
    size_kb = input_size / 1000
    threshold_ms = THRESHOLD_BASE_MS + (THRESHOLD_SCALE_MS_PER_KB * size_kb)
    return threshold_ms / 1000


def TestOneInput(data: bytes) -> None:  # noqa: N802 - Atheris required name
    """Atheris entry point: parse fuzzed input and measure time."""
    global _fuzz_stats  # noqa: PLW0602 - Required for crash-proof reporting

    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    try:
        source = fdp.ConsumeUnicodeNoSurrogates(MAX_INPUT_SIZE)
    except (UnicodeDecodeError, ValueError):
        source = data.decode("utf-8", errors="replace")[:MAX_INPUT_SIZE]

    parser = FluentParserV1()

    start = time.perf_counter()
    try:  # noqa: SIM105 - Need timing measurement after try block
        parser.parse(source)
    except (ValueError, RecursionError, MemoryError):
        pass  # Expected for invalid input
    duration = time.perf_counter() - start

    threshold = compute_threshold(len(source))
    if duration > threshold:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        ratio = duration / threshold
        print()
        print("=" * 80)
        print("[FINDING] PERFORMANCE BREACH DETECTED")
        print("=" * 80)
        print(f"Duration: {duration:.4f}s (threshold: {threshold:.4f}s)")
        print(f"Input size: {len(source)} chars")
        print(f"Ratio: {ratio:.2f}x threshold")
        print()
        print("Next steps:")
        print("  1. Review slow input: xxd .fuzz_corpus/crash_* | head -20")
        print("  2. Create performance test in tests/ with input as literal")
        print("  3. Profile and fix the algorithm")
        print("  4. See: docs/FUZZING_GUIDE.md (Bug Preservation Workflow)")
        print("=" * 80)
        msg = f"Complexity spike: {duration:.4f}s ({ratio:.2f}x threshold)"
        raise SlowParsing(msg)


def main() -> None:
    """Run the performance fuzzer."""
    print()
    print("=" * 80)
    print("Performance Fuzzer")
    print("=" * 80)
    print("Target: ReDoS and algorithmic complexity detection")
    print(f"Threshold: {THRESHOLD_BASE_MS}ms + {THRESHOLD_SCALE_MS_PER_KB}ms/KB")
    print("Press Ctrl+C to stop. Findings saved to .fuzz_corpus/crash_*")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
