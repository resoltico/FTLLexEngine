#!/usr/bin/env python3
"""Stability Fuzzer (Atheris).

Feeds random bytes to the parser and detects unexpected exceptions.
Expected exceptions (ValueError, RecursionError, MemoryError) are allowed.
Any other exception is reported as a finding.

Built for Python 3.13+ using modern PEPs (695, 585, 563).

Usage:
    ./scripts/fuzz.sh --native
    ./scripts/fuzz.sh --native --time 60
"""

from __future__ import annotations

import atexit
import json
import logging
import sys

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

# Suppress parser logging during fuzzing
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.parser import FluentParserV1


class StabilityBreachError(Exception):
    """Raised when an unexpected exception is detected during parsing."""


# Exception contract: only these exceptions are acceptable for invalid input
# - ValueError: Invalid syntax, encoding issues, constraint violations
# - RecursionError: Deeply nested input exceeding Python's recursion limit
# - MemoryError: Input too large to process
# - EOFError: Parser reached unexpected end of input (Cursor.current at EOF)
ALLOWED_EXCEPTIONS = (ValueError, RecursionError, MemoryError, EOFError)


def test_one_input(data: bytes) -> None:
    """Atheris entry point: parse fuzzed input and detect unexpected crashes."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # Limit source size to prevent OOM/timeouts in extremely large cases
    # although parsing 1MB is usually fine, fuzzer might generate deep nesting.
    try:
        source = fdp.ConsumeUnicodeNoSurrogates(1024 * 1024)
    except (UnicodeDecodeError, ValueError):
        # Use surrogateescape (PEP 383) for lossless round-trip preservation.
        # This matches repro.py decoding for consistent crash reproduction.
        source = data.decode("utf-8", errors="surrogateescape")

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
        print(f"Exception Type: {type(e).__module__}.{type(e).__name__}")
        print(f"Error Message: {e}")
        print(f"Input Length:  {len(source)} characters")
        print("-" * 80)
        print("NEXT STEPS:")
        print("  1. Reproduce:  ./scripts/fuzz.sh --repro .fuzz_corpus/crash_*")
        print("  2. Create test: Use tests/test_parser_survivability.py as template")
        print("  3. Fix & Verify: Resolve the crash and confirm with --repro")
        print("=" * 80)

        msg = f"{type(e).__name__}: {e}"
        raise StabilityBreachError(msg) from e


def main() -> None:
    """Run the stability fuzzer."""
    print()
    print("=" * 80)
    print("Fluent Stability Fuzzer (Python 3.13 Edition)")
    print("=" * 80)
    print("Target:   Parser crash detection")
    print("Contract: Only ValueError, RecursionError, MemoryError, EOFError allowed")
    print("Stopping: Press Ctrl+C at any time (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
