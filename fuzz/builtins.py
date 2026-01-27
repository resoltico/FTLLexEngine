#!/usr/bin/env python3
"""Built-in Function Boundary Fuzzer (Atheris).

Targets: NUMBER, DATETIME, CURRENCY functions.
Tests the bridge between FTL arguments and Babel/CLDR backend.

Built for Python 3.13+.
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
from datetime import UTC, datetime
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
    from ftllexengine.runtime.functions import currency_format, datetime_format, number_format

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test NUMBER, DATETIME, CURRENCY function boundaries."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Target Selection
    target = fdp.ConsumeIntInRange(0, 2)
    locale = fdp.PickValueInList(["en-US", "de-DE", "ar-EG", "zh-Hans-CN", "root"])

    try:
        if target == 0: # NUMBER
            val = Decimal(str(fdp.ConsumeFloat()))
            number_format(
                val,
                locale,
                minimum_fraction_digits=fdp.ConsumeIntInRange(0, 20),
                maximum_fraction_digits=fdp.ConsumeIntInRange(0, 20),
                use_grouping=fdp.ConsumeBool(),
                pattern=fdp.ConsumeUnicodeNoSurrogates(30) if fdp.ConsumeBool() else None
            )
        elif target == 1: # DATETIME
            # Limit to year 9999 for safe datetime range
            timestamp = fdp.ConsumeFloat() % 253402300799
            dt = datetime.fromtimestamp(timestamp, tz=UTC)
            time_pick = fdp.PickValueInList(["short", "medium", "long", "full"])
            datetime_format(
                dt,
                locale,
                date_style=fdp.PickValueInList(["short", "medium", "long", "full"]),
                time_style=time_pick if fdp.ConsumeBool() else None,
                pattern=fdp.ConsumeUnicodeNoSurrogates(30) if fdp.ConsumeBool() else None
            )
        else: # CURRENCY
            val = Decimal(str(fdp.ConsumeFloat()))
            currency_format(
                val,
                locale,
                currency=fdp.ConsumeUnicodeNoSurrogates(3),
                currency_display=fdp.PickValueInList(["symbol", "code", "name"]),
                pattern=fdp.ConsumeUnicodeNoSurrogates(30) if fdp.ConsumeBool() else None
            )
    except (ValueError, TypeError, OverflowError):
        pass # Expected for invalid patterns or Babel limitations
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
