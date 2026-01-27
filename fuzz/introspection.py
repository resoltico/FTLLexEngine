#!/usr/bin/env python3
"""Message Introspection Depth Fuzzer (Atheris).

Targets: ftllexengine.introspection.message.MessageIntrospection
Tests that introspection of complex/recursive messages never hange or crashes.

Built for Python 3.13+.
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
    from ftllexengine.syntax.parser import FluentParserV1

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test introspection of pathologically nested messages."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Generate pathologically nested FTL
    depth = fdp.ConsumeIntInRange(1, 100)
    ftl = "msg = " + ("{ msg" * depth) + " }" + (" }" * (depth - 1)) + "\n"

    parser = FluentParserV1()
    try:
        _ = parser.parse(ftl)

        # 2. Add to bundle and Introspect
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        # We need a message to introspect
        introspection = bundle.introspect_message("msg")
        if introspection:
            _ = introspection.variables
            _ = introspection.functions
            _ = introspection.references
            _ = introspection.has_selectors

    except (ValueError, RecursionError, MemoryError):
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
