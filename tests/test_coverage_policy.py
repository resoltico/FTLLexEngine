"""Tests enforcing the repository coverage policy configuration."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_enforces_full_line_and_branch_coverage() -> None:
    """Coverage config should require 100% and track branches."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    coverage_run = pyproject["tool"]["coverage"]["run"]
    coverage_report = pyproject["tool"]["coverage"]["report"]

    assert coverage_run["branch"] is True
    assert coverage_report["fail_under"] == 100.0


def test_scripts_test_sh_uses_same_coverage_threshold() -> None:
    """The main test script should match the pyproject coverage policy."""
    content = (REPO_ROOT / "scripts" / "test.sh").read_text(encoding="utf-8")

    match = re.search(r"^DEFAULT_COV_LIMIT=(\d+)$", content, re.MULTILINE)
    assert match is not None
    assert int(match.group(1)) == 100
