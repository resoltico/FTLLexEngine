#!/usr/bin/env python3
"""Cursor Integrity Fuzzer (Atheris).

Targets: ftllexengine.syntax.cursor.Cursor
Tests the low-level character streaming and position tracking logic.
"""

from __future__ import annotations

import atexit
import json
import logging
import sys

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
    from ftllexengine.syntax.cursor import Cursor, LineOffsetCache

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test Cursor and LineOffsetCache integrity."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    try:
        # 1. Normalize line endings (Cursor requirement)
        raw_source = fdp.ConsumeUnicodeNoSurrogates(1024)
        source = raw_source.replace("\r\n", "\n").replace("\r", "\n")

        # 2. Setup Cursor and Cache
        cursor = Cursor(source, 0)
        cache = LineOffsetCache(source)

        # 3. Random Navigation and Invariant Checks
        ops = fdp.ConsumeIntInRange(1, 20)
        for _ in range(ops):
            if cursor.is_eof:
                break

            # Check current
            curr = cursor.current
            assert curr == source[cursor.pos]

            # Check line:col consistency between Cursor and Cache
            c_line, c_col = cursor.compute_line_col()
            f_line, f_col = cache.get_line_col(cursor.pos)

            if (c_line, c_col) != (f_line, f_col):
                _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
                msg = (
                    f"Position mismatch at pos {cursor.pos}: "
                    f"Cursor({c_line}:{c_col}) != Cache({f_line}:{f_col})"
                )
                raise RuntimeError(msg)

            # Advance
            step = fdp.ConsumeIntInRange(1, 10)
            cursor = cursor.advance(step)

        # 4. Out-of-bounds Peek test
        offset = fdp.ConsumeIntInRange(0, 2000)
        _ = cursor.peek(offset)

    except (ValueError, EOFError):
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
