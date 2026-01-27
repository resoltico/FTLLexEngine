#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: templates - Error Template Integrity
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Error Template Integrity Fuzzer (Atheris).

Targets: ftllexengine.diagnostics.templates.ErrorTemplate
Tests that every static template method can handle arbitrary strings without crashing.
"""

from __future__ import annotations

import atexit
import inspect
import json
import logging
import sys
from typing import Any

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
    from ftllexengine.diagnostics.templates import ErrorTemplate

# Collect all static methods of ErrorTemplate
TEMPLATE_METHODS = [
    name for name, _ in inspect.getmembers(ErrorTemplate, predicate=inspect.isfunction)
    if not name.startswith("_")
]

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test error template methods with random arguments."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Pick a template method
    method_name = fdp.PickValueInList(TEMPLATE_METHODS)
    method = getattr(ErrorTemplate, method_name)

    # 2. Inspect signature to provide right number of args
    sig = inspect.signature(method)
    args = []
    kwargs: dict[str, Any] = {}

    for param in sig.parameters.values():
        if param.default is not inspect.Parameter.empty and fdp.ConsumeBool():
            continue  # skip optional

        # Use identity comparison for types
        if param.annotation is int:
            args.append(fdp.ConsumeInt(4))
        elif hasattr(param.annotation, "__origin__") and param.annotation.__origin__ is list:
            args.append([fdp.ConsumeUnicodeNoSurrogates(10) for _ in range(3)])
        else:
            args.append(fdp.ConsumeUnicodeNoSurrogates(20))

    # 3. Call
    try:
        diag = method(*args, **kwargs)
        # Check invariants
        assert hasattr(diag, "message")
        assert hasattr(diag, "code")
    except (ValueError, TypeError):
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
