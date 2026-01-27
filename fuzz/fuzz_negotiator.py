#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: negotiator - Locale BCP 47 Negotiation & Normalization
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Locale Negotiator Fuzzer (Atheris).

Targets: ftllexengine.locale_utils and FluentLocalization fallback
Tests BCP 47 subtag matching and locale chain negotiation.
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
    from ftllexengine.locale_utils import normalize_locale
    from ftllexengine.localization import FluentLocalization

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test locale normalization and negotiation."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    try:
        # 1. Test Normalization
        raw_locale = fdp.ConsumeUnicodeNoSurrogates(30)
        if raw_locale:
            norm = normalize_locale(raw_locale)
            # Idempotence
            assert normalize_locale(norm) == norm

        # 2. Test negotiation with random chain
        chain = [fdp.ConsumeUnicodeNoSurrogates(10) for _ in range(3)]
        if all(chain):
            l10n = FluentLocalization(chain)
            _ = l10n.locales

    except (ValueError, TypeError):
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
