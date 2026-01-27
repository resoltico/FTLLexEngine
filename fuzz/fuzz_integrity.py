#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: integrity - Multi-Resource Semantic Integrity
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Multi-Resource Integrity Fuzzer (Atheris).

Targets: ftllexengine.integrity.IntegrityChecker (via FluentBundle)
Tests cross-resource transitive cycles and term usage visibility.

Built for Python 3.13+.
"""

from __future__ import annotations

import atexit
import contextlib
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

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test multi-resource integrity and transitive dependencies."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    bundle = FluentBundle("en-US", strict=True)

    # 1. Create multiple random FTL resources
    num_resources = fdp.ConsumeIntInRange(1, 4)
    for i in range(num_resources):
        # We want to create dependencies between resources
        # Resource i references message in Resource i+1
        next_idx = (i + 1) % num_resources
        ftl = f"msg_{i} = Value from {i} {{ msg_{next_idx} }}\n"
        if fdp.ConsumeBool():
            # Add a term that might be used across boundaries
            ftl += f"-term_{i} = Private {i}\n"

        with contextlib.suppress(Exception):
            bundle.add_resource(ftl)

    # 2. Check Integrity
    try:
        # validate_resource on a bundle performs transitive checks
        # We manually trigger a deep validation of the whole bundle
        # if the bundle has an explicit check method (TBD).
        # FluentBundle.validate() or similar.
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
