#!/usr/bin/env python3
"""Performance Fuzzer (Atheris).

Detects algorithmic complexity attacks (ReDoS, quadratic behavior).
Measures parse time and flags inputs that exceed size-scaled thresholds.

Usage:
    ./scripts/fuzz-atheris.sh 4 fuzz/perf.py
    ./scripts/fuzz-atheris.sh 4 fuzz/perf.py -max_total_time=60
"""

from __future__ import annotations

import sys
import time

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

with atheris.instrument_imports():
    from ftllexengine.syntax.parser import FluentParserV1


class SlowParsing(Exception):  # noqa: N818 - Domain-specific name
    """Raised when parsing exceeds the time threshold."""


# Threshold model accounting for Atheris ~30-50x instrumentation overhead
THRESHOLD_BASE_MS = 100  # Floor: instrumentation startup
THRESHOLD_SCALE_MS_PER_KB = 20  # Catches O(N^2), ignores linear O(N)
MAX_INPUT_SIZE = 50000  # Limit input size for performance testing


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
