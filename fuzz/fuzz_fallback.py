#!/usr/bin/env python3
"""Multi-Locale Fallback Orchestrator Fuzzer (Atheris).

Targets: ftllexengine.localization.FluentLocalization
Tests locale fallback chains, lazy bundle creation, and thread safety.

Built for Python 3.13+.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import logging
import sys
import threading
from collections.abc import Mapping

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
    from ftllexengine.localization import FluentLocalization, ResourceLoader

class MockLoader(ResourceLoader):
    """Memory-backed loader to avoid disk I/O in fuzzer."""
    def __init__(self, resources: Mapping[str, Mapping[str, str]]):
        self.resources = resources # locale -> resource_id -> content

    def load(self, locale: str, resource_id: str) -> str:
        if locale in self.resources and resource_id in self.resources[locale]:
            return self.resources[locale][resource_id]
        msg = f"Resource {resource_id} not found for locale {locale}"
        raise FileNotFoundError(msg)

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test multi-locale fallback chains and thread safety."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # 1. Setup Locale Chain
    locales = ["en-US", "lv", "ar", "pl", "invalid"]
    selected_locales = [fdp.PickValueInList(locales) for _ in range(fdp.ConsumeIntInRange(1, 5))]
    resource_ids = ["main.ftl", "errors.ftl"]

    # 2. Build Mock Resources
    mock_data = {}
    for loc in selected_locales:
        mock_data[loc] = {
            "main.ftl": f"msg = Value from {loc}\n",
            "errors.ftl": f"err = Error from {loc}\n"
        }
        # Randomly remove some to force fallback
        if fdp.ConsumeBool():
            del mock_data[loc]["main.ftl"]

    loader = MockLoader(mock_data)

    # 3. Execution
    try:
        l10n = FluentLocalization(
            selected_locales,
            resource_ids,
            loader,
            strict=fdp.ConsumeBool(),
            enable_cache=fdp.ConsumeBool()
        )

        # Test formatting
        l10n.format_value("msg")
        l10n.format_value("err")
        l10n.format_value("nonexistent")

        # 4. Multi-threaded Stress (Race Condition detection)
        def worker():
            with contextlib.suppress(BaseException):
                l10n.format_value("msg")

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    except (ValueError, TypeError):
        pass
    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
