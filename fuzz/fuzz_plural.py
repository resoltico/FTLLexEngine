#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: plural - Plural Rule Boundary & CLDR
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Plural Rule Boundary Fuzzer (Atheris).

Targets: ftllexengine.runtime.plural_rules.select_plural_category
Tests the precision-aware CLDR plural categorization logic.

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
    from ftllexengine.runtime.plural_rules import select_plural_category

# High-leverage locales for plural testing
# lv: zero, one, other (decimal)
# ru: one, few, many, other
# ar: zero, one, two, few, many, other (most complex)
# en: one, other
# ja: other (no plurals)
TEST_LOCALES = ["en", "lv", "ru", "ar", "ja", "pl", "root", "invalid-locale"]

VALID_CATEGORIES = {"zero", "one", "two", "few", "many", "other"}

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test plural category selection precision."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Select inputs
    use_test_locale = fdp.ConsumeBool()
    locale = (
        fdp.PickValueInList(TEST_LOCALES)
        if use_test_locale
        else fdp.ConsumeUnicodeNoSurrogates(10)
    )

    # Selection of number types
    num_type = fdp.ConsumeIntInRange(0, 2)
    try:
        if num_type == 0:
            n = fdp.ConsumeInt(8)
        elif num_type == 1:
            n = fdp.ConsumeFloat()
        else:
            # Generate a "logical" decimal string
            n = Decimal(str(fdp.ConsumeFloat()))
    except (ValueError, OverflowError):
        return

    # Precision: None or 0-10
    precision = fdp.ConsumeIntInRange(0, 10) if fdp.ConsumeBool() else None

    # 2. Execute
    try:
        category = select_plural_category(n, locale, precision=precision)

        # 3. Invariants
        if category not in VALID_CATEGORIES:
            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            msg = f"Invalid plural category returned: {category}"
            raise RuntimeError(msg)

    except (ValueError, TypeError):
        pass # Expected for truly broken inputs/locales if not caught by root fallback
    except Exception as e:
        if "Babel" in str(e): # Babel missing should not be a crash but we check setup in preflight
            return
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
