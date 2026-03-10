#!/usr/bin/env python3
# @lint-plugin: PyEnv
"""Diagnostic plugin: validate the Python environment used by lint plugins.

Reports the Python version, PYTHONPATH, installed package version, and
whether `ftllexengine` can be imported cleanly. Fails if the Python running
this plugin is older than the project minimum (3.13) OR if the package
cannot be imported.

This plugin is a dead-man's switch for the "Python 3.12 system python runs
plugins" class of CI failure: the plugin runner in lint.sh uses bare `python`,
which may resolve to the system Python rather than the venv Python. When the
system Python is older than the required minimum, importing ftllexengine may
fail because the package uses Python 3.13+ features (e.g. TypeIs from PEP 742).

Exit Codes:
    0: Environment is correct (Python >= 3.13, package importable)
    1: Python version too old or package not importable
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

_MIN_PYTHON = (3, 13)
_SCRIPT_DIR = Path(__file__).parent
ROOT = _SCRIPT_DIR.parent
PYPROJECT = ROOT / "pyproject.toml"


def _get_required_python() -> tuple[int, int]:
    """Read requires-python from pyproject.toml."""
    try:
        with PYPROJECT.open("rb") as f:
            data = tomllib.load(f)
        req = data.get("project", {}).get("requires-python", ">=3.13")
        # Parse ">= 3.13" or ">=3.13" → (3, 13)
        req = req.strip().lstrip(">= ")
        parts = req.split(".")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except Exception:  # pylint: disable=broad-exception-caught
        # Fallback: if pyproject.toml is unreadable or malformed, use hardcoded minimum.
        return _MIN_PYTHON


def _try_import() -> tuple[bool, str]:
    """Attempt to import ftllexengine and return (success, detail)."""
    try:
        import ftllexengine  # noqa: PLC0415  # pylint: disable=C0415
        version = getattr(ftllexengine, "__version__", "<no __version__>")
        return True, f"version={version}"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Diagnostic tool: intentionally catches all import failures to report them.
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    """Run environment validation. Returns 0 on pass, 1 on failure."""
    failures: list[str] = []
    warnings: list[str] = []

    # 1. Python version check
    current = sys.version_info[:2]
    required = _get_required_python()

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
    importable, detail = _try_import()
    if importable:
        print(f"  [PASS] import ftllexengine succeeded ({detail})")
    else:
        failures.append(
            f"import ftllexengine failed: {detail}\n"
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
