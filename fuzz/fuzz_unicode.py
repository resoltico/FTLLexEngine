#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: unicode - Unicode Normalization & Surrogates
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Unicode Normalization & Surrogate Fuzzer (Atheris).

Targets: ftllexengine.syntax.parser.FluentParserV1
Tests identifier stability across normalization forms and surrogate pairs.

Built for Python 3.13+.
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
import unicodedata

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
    from ftllexengine.syntax.parser import FluentParserV1

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test unicode normalization and identifier stability."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Generate Tricky Unicode Identifier
    try:
        raw_id = fdp.ConsumeUnicodeNoSurrogates(20)
        if not raw_id:
            return

        # Randomly apply normalization
        forms = ["NFC", "NFD", "NFKC", "NFKD"]
        norm_form = fdp.PickValueInList(forms)
        normalized_id = unicodedata.normalize(norm_form, raw_id)

        # 2. Construct FTL containing the ID
        # Note: Fluent IDs must start with [a-zA-Z], so we prefix.
        ftl = f"msg_{normalized_id} = Value\n"

    except (ValueError, UnicodeEncodeError):
        return

    parser = FluentParserV1()

    # 3. Parse and Verify
    try:
        res = parser.parse(ftl)

        # Check if ID was preserved (ignoring spans/positions)
        if not any(type(e).__name__ == "Junk" for e in res.entries):
            # Verify parsed ID matches our normalized_id
            found = False
            for entry in res.entries:
                if hasattr(entry, "id") and entry.id.name == f"msg_{normalized_id}":
                    found = True
                    break

            # If not found but also no Junk, this is a logic bug
            if not found and res.entries:
                _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
                msg = "Parsed message ID mismatch"
                raise RuntimeError(msg)

    except (ValueError, RecursionError):
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
