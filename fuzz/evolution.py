#!/usr/bin/env python3
"""Stateful Bundle Evolution Fuzzer (Atheris).

Targets: ftllexengine.runtime.bundle.FluentBundle
Tests resource overwriting, cache invalidation, and incremental additions.

Stresses the internal state consistency of the bundle across multiple mutations.
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
    """Atheris entry point: Test incremental bundle mutations and cache invalidation."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    bundle = FluentBundle("en-US", enable_cache=True)
    in_flight_messages = {}

    # Perform a series of bundle mutations
    num_ops = fdp.ConsumeIntInRange(1, 10)
    for _ in range(num_ops):
        op = fdp.ConsumeIntInRange(0, 1)

        if op == 0: # Add Resource
            msg_id = f"msg_{fdp.ConsumeIntInRange(0, 5)}"
            val = fdp.ConsumeUnicodeNoSurrogates(20)
            ftl = f"{msg_id} = {val}\n"

            try:
                bundle.add_resource(ftl)
                # First one wins in Fluent for the same bundle instance
                if msg_id not in in_flight_messages:
                    in_flight_messages[msg_id] = val
            except Exception:  # pylint: disable=broad-exception-caught # Fuzzer: silently skip invalid resource mutations
                pass
        else: # Verify Resource
            if not in_flight_messages:
                continue
            msg_id = f"msg_{fdp.ConsumeIntInRange(0, 5)}"
            if msg_id in in_flight_messages:
                res, _ = bundle.format_value(msg_id)
                # In most cases, res should contain the value or a fallback
                # but we specifically check for formatting stability
                if not isinstance(res, str):
                    _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
                    msg = f"Evolution failed: {msg_id} produced non-string"
                    raise RuntimeError(msg)

    # Final check: cache collision stress
    for msg_id, _ in in_flight_messages.items():
        val1, _ = bundle.format_value(msg_id)
        val2, _ = bundle.format_value(msg_id)
        if val1 != val2:
            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            msg = f"Cache collision or non-determinism for {msg_id}: '{val1}' != '{val2}'"
            raise RuntimeError(msg)

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
