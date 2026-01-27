#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: security - I/O and Path Security (Traversal)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""I/O & Path Security Fuzzer (Atheris).

Targets: ftllexengine.localization.PathResourceLoader
Tests for directory traversal and safe path resolution.

Built for Python 3.13+.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import logging
import sys
import tempfile
from pathlib import Path

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
    from ftllexengine.localization import PathResourceLoader

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test path traversal and safe resolution in PathResourceLoader."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Setup root and locale structure
        root = Path(tmp_dir) / "locales"
        root.mkdir()
        (root / "en").mkdir()
        (root / "en" / "main.ftl").write_text("ok = OK")

        # 2. Setup Loader
        # We use a path template that includes the placeholder
        loader = PathResourceLoader(str(root / "{locale}"))

        # 3. Fuzz locale and resource_id
        try:
            locale = fdp.ConsumeUnicodeNoSurrogates(50)
            resource_id = fdp.ConsumeUnicodeNoSurrogates(50)

            if not locale or not resource_id:
                return

            # Attempt load
            with contextlib.suppress(ValueError, FileNotFoundError, OSError):
                loader.load(locale, resource_id)

        except Exception:
            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
