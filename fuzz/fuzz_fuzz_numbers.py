#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: fuzz_numbers - Numeric Parser Unit
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Numeric Parser Unit Fuzzer (Atheris).

Targets: ftllexengine.parsing.numbers
Tests locale-aware float and decimal extraction.
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
    from ftllexengine.parsing.numbers import parse_decimal, parse_number

TEST_LOCALES = ["en-US", "de-DE", "lv-LV", "ar-SA", "root"]

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test locale-aware number parsing."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    use_test_locale = fdp.ConsumeBool()
    locale = (
        fdp.PickValueInList(TEST_LOCALES)
        if use_test_locale
        else fdp.ConsumeUnicodeNoSurrogates(10)
    )
    input_str = fdp.ConsumeUnicodeNoSurrogates(50)

    if not input_str or not locale:
        return

    try:
        # Test Float
        res_f, _ = parse_number(input_str, locale)
        if res_f is not None:
            assert isinstance(res_f, float)

        # Test Decimal
        res_d, _ = parse_decimal(input_str, locale)
        if res_d is not None:
            assert isinstance(res_d, Decimal)

    except (ValueError, TypeError):
        pass
    except OverflowError: # Large exponents in str -> float
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
