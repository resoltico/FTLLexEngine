#!/usr/bin/env python3
"""Variable Shadowing & Term Scope Fuzzer (Atheris).

Targets: ftllexengine.runtime.bundle.FluentBundle
Tests local variable isolation and term argument scope consistency.
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
    from ftllexengine.runtime.bundle import FluentBundle

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test variable shadowing and term scope isolation."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Create shadowing FTL
    # Use $var in message and also in term arguments.
    # Fluent spec says terms have their own argument scope.
    ftl = """
msg = { $var } - { -term(var: "term-local") } - { $var }
-term = { $var } (shadowed)
"""
    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(ftl)

    # 2. Execution
    try:
        ext_var = fdp.ConsumeUnicodeNoSurrogates(10)
        res, _ = bundle.format_value("msg", {"var": ext_var})

        # Invariant: External $var should be preserved around the term call
        expected_part = f"{ext_var} - term-local (shadowed) - {ext_var}"
        if res != expected_part:
            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            msg = f"Shadowing Failure: expected '{expected_part}', got '{res}'"
            raise RuntimeError(msg)

    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
