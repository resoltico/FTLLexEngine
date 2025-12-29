#!/usr/bin/env python3
"""Stability Fuzzer (Atheris).

Feeds random bytes to the parser and detects unexpected exceptions.
Expected exceptions (ValueError, RecursionError, MemoryError) are allowed.
Any other exception is reported as a finding.

Usage:
    ./scripts/fuzz-atheris.sh 4 fuzz/stability.py
    ./scripts/fuzz-atheris.sh 4 fuzz/stability.py -max_total_time=60
"""

from __future__ import annotations

import atexit
import json
import logging
import sys

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

# Suppress parser logging during fuzzing
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports():
    from ftllexengine.syntax.parser import FluentParserV1


class UnexpectedCrash(Exception):  # noqa: N818 - Domain-specific name
    """Raised when an unexpected exception is detected."""


# Exception contract: only these exceptions are acceptable for invalid input
ALLOWED_EXCEPTIONS = (ValueError, RecursionError, MemoryError)


def TestOneInput(data: bytes) -> None:  # noqa: N802 - Atheris required name
    """Atheris entry point: parse fuzzed input and detect unexpected crashes."""
    global _fuzz_stats  # noqa: PLW0602 - Required for crash-proof reporting

    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    try:
        source = fdp.ConsumeUnicodeNoSurrogates(len(data))
    except (UnicodeDecodeError, ValueError):
        source = data.decode("utf-8", errors="replace")

    parser = FluentParserV1(max_source_size=1024 * 1024, max_nesting_depth=100)

    try:
        parser.parse(source)
    except ALLOWED_EXCEPTIONS:
        pass  # Expected for invalid input
    except Exception as e:
        # Unexpected exception - this is a finding
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        _fuzz_stats["status"] = "finding"

        print()
        print("=" * 80)
        print("[FINDING] STABILITY BREACH DETECTED")
        print("=" * 80)
        print(f"Exception: {type(e).__name__}: {e}")
        print(f"Input size: {len(source)} chars")
        print()
        print("Next steps:")
        print("  1. Reproduce: ./scripts/fuzz.sh --repro .fuzz_corpus/crash_*")
        print("  2. Create unit test in tests/ with crash input as literal")
        print("  3. Fix the bug, run tests to confirm")
        print("  4. See: docs/FUZZING_GUIDE.md (Bug Preservation Workflow)")
        print("=" * 80)
        msg = f"{type(e).__name__}: {e}"
        raise UnexpectedCrash(msg) from e


def main() -> None:
    """Run the stability fuzzer."""
    print()
    print("=" * 80)
    print("Stability Fuzzer")
    print("=" * 80)
    print("Target: Parser crash detection")
    print("Contract: Only ValueError, RecursionError, MemoryError allowed")
    print("Press Ctrl+C to stop. Findings saved to .fuzz_corpus/crash_*")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
