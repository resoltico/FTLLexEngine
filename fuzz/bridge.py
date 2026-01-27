#!/usr/bin/env python3
"""Argument Bridge Type Coercion Fuzzer (Atheris).

Targets: ftllexengine.runtime.function_bridge.FunctionRegistry
Tests how the bridge handles adversarial Python objects passed as variables.
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

class EvilObject:
    """An object designed to crash string conversion or hashing."""
    def __init__(self, mode: int):
        self.mode = mode

    def __str__(self) -> str:
        if self.mode == 0:
            msg = "Evil __str__"
            raise RuntimeError(msg)
        return "evil"

    def __repr__(self) -> str:
        if self.mode == 1:
            msg = "Evil __repr__"
            raise RuntimeError(msg)
        return "evil_repr"

    def __hash__(self) -> int:
        if self.mode == 2:
            msg = "Unhashable evil"
            raise TypeError(msg)
        return 42

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test type coercion with adversarial objects."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # Static FTL that uses the variable
    ftl = "msg = Value: { $var }\nattr = { msg.title }\n  .title = { $var }\n"

    bundle = FluentBundle("en-US", enable_cache=fdp.ConsumeBool())
    bundle.add_resource(ftl)

    # 1. Select payload (type: ignore for intentional type variance in fuzzing)
    mode = fdp.ConsumeIntInRange(0, 5)
    var: object
    if mode < 3:
        var = EvilObject(mode)
    elif mode == 3:
        # Recursive list
        recursive_list: list[object] = []
        recursive_list.append(recursive_list)
        var = recursive_list
    elif mode == 4:
        # Recursive dict
        recursive_dict: dict[str, object] = {}
        recursive_dict["self"] = recursive_dict
        var = recursive_dict
    else:
        # Massive string
        var = "A" * 10000

    # 2. Execute resolution
    try:
        # format_value handles string conversion
        _ = bundle.format_value("msg", {"var": var})  # type: ignore[dict-item]
        _ = bundle.format_value("attr", {"var": var})  # type: ignore[dict-item]
    except (RuntimeError, TypeError, RecursionError):
        pass # Expected for truly evil objects
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
