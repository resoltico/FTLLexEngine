#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: roundtrip - Metamorphic roundtrip (Parser <-> Serializer)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Metamorphic Roundtrip Fuzzer (Atheris).

Targets the Parser-Serializer identity:
Source -> AST1 -> Serialized1 -> AST2 -> Serialized2

Invariants:
1. Serialized1 must parse successfully to AST2.
2. Serialized1 must equal Serialized2 (Convergence).
3. (Optional) AST1 structural equality with AST2 (ignoring spans).

Built for Python 3.13+ using modern PEPs (695, 585, 563).
"""

from __future__ import annotations

import atexit
import json
import logging
import sys

# --- PEP 695 Type Aliases (Python 3.13) ---
type FuzzStats = dict[str, int | str]

# Crash-proof reporting
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}

def _emit_final_report() -> None:
    """Emit JSON summary on exit."""
    report = json.dumps(_fuzz_stats)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)

atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    print("Error: atheris not found. See docs/FUZZING_GUIDE.md")
    sys.exit(1)

# Suppress logging
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.parser import FluentParserV1
    from ftllexengine.syntax.serializer import serialize

class RoundtripError(Exception):
    """Raised when a roundtrip invariant is breached."""

def test_one_input(data: bytes) -> None:
    """Atheris entry point: verify parse-serialize roundtrip."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)
    try:
        source = fdp.ConsumeUnicodeNoSurrogates(1024 * 64) # 64KB limit for roundtrip performance
    except (UnicodeDecodeError, ValueError):
        return

    parser = FluentParserV1()

    # 1. First Parse
    try:
        ast1 = parser.parse(source)
    except (ValueError, RecursionError, MemoryError):
        return # Valid parser rejection

    # Skip if we found Junk (syntax errors).
    # Roundtripping Junk is Best-Effort, but logically we want to test Valid FTL.
    if any(type(e).__name__ == "Junk" for e in ast1.entries):
        return

    # 2. Serialize
    try:
        serialized1 = serialize(ast1)
    except Exception as e:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        print(f"\n[FAIL] Serialization failed for valid AST: {e}")
        msg = f"Serialization failed: {e}"
        raise RoundtripError(msg) from e

    # 3. Second Parse
    try:
        ast2 = parser.parse(serialized1)
    except Exception as e:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        print(f"\n[FAIL] Serialized output failed to re-parse: {e}")
        print(f"Serialized output:\n{serialized1}")
        msg = f"Re-parse failed: {e}"
        raise RoundtripError(msg) from e

    # 4. Final Serialization (Convergence)
    try:
        serialized2 = serialize(ast2)
    except Exception as e:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        msg = f"Second serialization failed: {e}"
        raise RoundtripError(msg) from e

    # INVARIANT: Serialized output must converge
    if serialized1 != serialized2:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        print("\n" + "="*80)
        print("[FINDING] ROUNDTRIP DIVERGENCE (Non-convergent)")
        print("="*80)
        print(f"Original source: {len(source)} chars")
        print("-" * 40)
        print(f"Serialized 1:\n{serialized1}")
        print("-" * 40)
        print(f"Serialized 2:\n{serialized2}")
        print("="*80)
        msg = "Roundtrip did not converge (Serialized1 != Serialized2)"
        raise RoundtripError(msg)

def main() -> None:
    """Run the roundtrip fuzzer."""
    sys.setrecursionlimit(2000)
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()

if __name__ == "__main__":
    main()
