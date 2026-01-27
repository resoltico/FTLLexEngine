#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: currency - Currency symbol & numeric extraction
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Currency Parsing Fuzzer (Atheris).

Targets: ftllexengine.parsing.currency.parse_currency
Tests tiered loading, ambiguous symbol resolution, and numeric extraction.

Built for Python 3.13+.
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
    from ftllexengine.parsing.currency import parse_currency

TEST_LOCALES = ["en-US", "en-CA", "zh-CN", "lv-LV", "ar-EG", "root"]

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test currency parsing boundary conditions."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Inputs
    use_test_locale = fdp.ConsumeBool()
    locale = (
        fdp.PickValueInList(TEST_LOCALES)
        if use_test_locale
        else fdp.ConsumeUnicodeNoSurrogates(10)
    )
    input_str = fdp.ConsumeUnicodeNoSurrogates(50)
    default_curr = fdp.ConsumeUnicodeNoSurrogates(3) if fdp.ConsumeBool() else None
    infer = fdp.ConsumeBool()

    if not input_str or not locale:
        return

    # 2. Execution
    try:
        res, _ = parse_currency(
            input_str,
            locale,
            default_currency=default_curr,
            infer_from_locale=infer
        )
        if res:
            amount, code = res
            assert isinstance(amount, Decimal)
            assert isinstance(code, str)
            assert len(code) == 3

    except (ValueError, TypeError):
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
