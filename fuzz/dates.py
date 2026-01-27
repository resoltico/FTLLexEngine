#!/usr/bin/env python3
"""Locale-Aware Date/Datetime Parsing Fuzzer (Atheris).

Targets: ftllexengine.parsing.dates
Tests the Babel/CLDR to strptime mapping logic.

Built for Python 3.13+.
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
from datetime import date, datetime

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
    from ftllexengine.parsing.dates import parse_date, parse_datetime

# Selection of problematic or interesting locales
TEST_LOCALES = [
    "en-US", "en-GB", "de-DE", "fr-FR", "ja-JP",
    "ar-SA", "ru-RU", "zh-Hans-CN", "lv-LV", "th-TH",
    "root", "invalid"
]

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test locale-aware date/datetime parsing."""
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

    if not input_str or not locale:
        return

    # 2. Execution
    try:
        # Test Date Parser
        res_date, _ = parse_date(input_str, locale)
        if res_date:
            assert isinstance(res_date, date)

        # Test DateTime Parser
        res_dt, _ = parse_datetime(input_str, locale)
        if res_dt:
            assert isinstance(res_dt, datetime)

    except (ValueError, TypeError):
        pass # Expected for truly broken inputs
    except OverflowError:
        pass # Expected for date ranges > 9999
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
