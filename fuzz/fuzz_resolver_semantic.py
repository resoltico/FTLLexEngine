#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: resolver_semantic - Resolver Semantic Logic
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Resolver Semantic Fuzzer (Atheris).

Targets: ftllexengine.runtime.bundle.FluentBundle.format_value
Tests the logical correctness of value resolution with complex arguments.
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
from decimal import Decimal

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

# Static complex FTL to test various resolution paths
COMPLEX_FTL = """
# Variables and Attributes
msg-var = Value is { $var }
msg-attr = Attribute is { msg-var.title }
    .title = Subtitle

# Select Expressions
msg-select = { $count ->
    [one] One item
   *[other] { $count } items
}

# Nested calls
msg-nested = Nested { -term(arg: $var) }
-term = Term with { $arg }
"""

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test resolver with complex argument types."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(COMPLEX_FTL)

    # Fuzz arguments
    args = {}

    # var: selection of types
    var_type = fdp.ConsumeIntInRange(0, 4)
    if var_type == 0:
        args["var"] = fdp.ConsumeUnicodeNoSurrogates(20)
    elif var_type == 1:
        args["var"] = fdp.ConsumeInt(8)
    elif var_type == 2:
        args["var"] = Decimal(str(fdp.ConsumeFloat()))
    elif var_type == 3:
        args["var"] = [fdp.ConsumeInt(4) for _ in range(3)] # List (should be handled by bridge)
    else:
        args["var"] = {"nested": "value"} # Dict

    # count: usually int/decimal for select
    if fdp.ConsumeBool():
        args["count"] = fdp.ConsumeIntInRange(-10, 100)

    # 2. Execute
    try:
        for msg_id in ["msg-var", "msg-attr", "msg-select", "msg-nested"]:
            val, _ = bundle.format_value(msg_id, args)

            # Invariant: val must be a string even if errors occur
            if not isinstance(val, str):
                _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
                msg = f"Non-string returned for {msg_id}: {type(val)}"
                raise RuntimeError(msg)

    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
