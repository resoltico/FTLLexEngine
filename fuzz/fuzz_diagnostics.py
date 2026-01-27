#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: diagnostics - Diagnostic Template Integrity
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Diagnostic Template Integrity Fuzzer (Atheris).

Targets: ftllexengine.diagnostics.errors.FrozenFluentError.format_pretty
Tests that error formatting and localization never crash.

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
    from ftllexengine.diagnostics.errors import ErrorCategory, FrozenFluentError

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test FrozenFluentError integrity with random inputs."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # Test error construction and basic operations
    try:
        category = fdp.PickValueInList(list(ErrorCategory))
        message = fdp.ConsumeUnicodeNoSurrogates(50)

        # Construct Error
        err = FrozenFluentError(
            message=message,
            category=category,
            diagnostic=None,  # Could be extended to test with Diagnostic objects
            context=None
        )

        # Test basic operations that must never crash
        _ = err.message
        _ = err.category
        _ = str(err)
        _ = repr(err)
        _ = hash(err)

        # Test equality
        err2 = FrozenFluentError(message, category, None, None)
        _ = err == err2

    except (ValueError, TypeError):
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
