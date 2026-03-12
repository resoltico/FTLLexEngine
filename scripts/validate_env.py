#!/usr/bin/env python3
# @lint-plugin: PyEnv
"""Diagnostic plugin: validate the Python environment used by lint plugins.

Philosophy:
    Environment bleed (the system Python slipping into isolated CI runners) is
    the #1 cause of flaky linting and tests. This plugin is a universal,
    project-agnostic "dead-man's switch" that guarantees the environment
    executing it matches the strict requirements of the project.

Architecture & Specs:
    This script relies on `pyproject.toml` as the single source of truth for
    project metadata. It strictly requires:
    1. `[project].name`: Used to dynamically resolve the package for the
       import test (verifying C-extensions, dependencies, and syntax).
    2. `[project].requires-python`: Used to dynamically set the floor version
       for `sys.version_info` (e.g., `>=3.13`).

    If the environment falls below this floor, or if the package cannot imported,
    the plugin deliberately catches the failure and emits a high-signal
    diagnostic message explaining *exactly* how to fix the CI runner.

Exit Codes:
    0: Environment is correct (Python >= required, package importable)
    1: Environment bleed detected (version too old or package not importable)
"""

from __future__ import annotations

import importlib
import os
import sys
import tomllib
from pathlib import Path

_FALLBACK_MIN_PYTHON = (3, 8)
_SCRIPT_DIR = Path(__file__).parent
ROOT = _SCRIPT_DIR.parent
PYPROJECT = ROOT / "pyproject.toml"


def _read_project_metadata() -> tuple[tuple[int, int], str]:
    """Read minimum python version and package name from pyproject.toml."""
    try:
        with PYPROJECT.open("rb") as f:
            data = tomllib.load(f)
        project = data.get("project", {})

        # Parse ">=3.14,<3.15" or ">=3.13" → (3, 14).
        # Split on comma first to isolate the lower-bound specifier before stripping operators.
        raw = project.get("requires-python", ">=3.8")
        lower = raw.split(",")[0].strip().lstrip(">= ")
        parts = lower.split(".")
        min_py = (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)

        # Parse package name, falling back to guessing from src/ if missing
        pkg_name = project.get("name", "")
        if not pkg_name:
            src_dir = ROOT / "src"
            subdirs = [
                d.name for d in src_dir.iterdir()
                if d.is_dir() and d.name != "__pycache__" and not d.name.endswith(".egg-info")
            ]
            pkg_name = subdirs[0] if len(subdirs) == 1 else "unknown_package"

        return min_py, pkg_name.replace("-", "_")
    except Exception:  # pylint: disable=broad-exception-caught
        return _FALLBACK_MIN_PYTHON, "unknown_package"


def _try_import(pkg_name: str) -> tuple[bool, str]:
    """Attempt to import the project package and return (success, detail)."""
    if pkg_name == "unknown_package":
        return False, "Could not determine package name from pyproject.toml or src/ directory"

    try:
        module = importlib.import_module(pkg_name)
        version = getattr(module, "__version__", "<no __version__>")
        return True, f"version={version}"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Diagnostic tool: intentionally catches all import failures to report them.
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    """Run environment validation. Returns 0 on pass, 1 on failure."""
    failures: list[str] = []
    warnings: list[str] = []

    required, pkg_name = _read_project_metadata()
    current = sys.version_info[:2]

    print(f"  Python binary  : {sys.executable}")
    print(f"  Python version : {sys.version}")
    print(f"  Required        : >={required[0]}.{required[1]}")
    print(f"  PYTHONPATH      : {os.environ.get('PYTHONPATH', '<not set>')}")
    print(f"  VIRTUAL_ENV     : {os.environ.get('VIRTUAL_ENV', '<not set>')}")
    print(f"  sys.prefix      : {sys.prefix}")

    if current < required:
        failures.append(
            f"Python {current[0]}.{current[1]} is below required >={required[0]}.{required[1]}.\n"
            f"  The lint plugin runner (scripts/lint.sh) uses bare `python`, which\n"
            f"  resolved to the system Python ({sys.executable}) rather than the\n"
            f"  venv Python. Fix: change the plugin runner to use the venv Python:\n"
            f'    if [[ "$file" == *.py ]]; then cmd=("${{TARGET_VENV}}/bin/python" "$file")'
        )
    else:
        print(f"  [PASS] Python {current[0]}.{current[1]} >= {required[0]}.{required[1]}")

    # 2. Package import check
    importable, detail = _try_import(pkg_name)
    if importable:
        print(f"  [PASS] import {pkg_name} succeeded ({detail})")
    else:
        failures.append(
            f"import {pkg_name} failed: {detail}\n"
            f"  Likely cause: Python version incompatibility or PYTHONPATH misconfiguration."
        )

    # 3. venv consistency check
    venv = os.environ.get("VIRTUAL_ENV", "")
    if venv and not sys.executable.startswith(venv):
        warnings.append(
            f"VIRTUAL_ENV={venv!r} but sys.executable={sys.executable!r}.\n"
            f"  The plugin is NOT running in the expected venv. The system Python\n"
            f"  is being used instead. This is the root cause of version-related\n"
            f"  plugin failures."
        )

    if warnings:
        for w in warnings:
            print(f"  [WARN] {w}")

    if failures:
        print("\n[FAIL] PyEnv: environment check failed")
        for f in failures:
            print(f"  {f}")
        return 1

    print("[PASS] PyEnv: environment is correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
