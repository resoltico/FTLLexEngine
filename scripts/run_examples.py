#!/usr/bin/env python3
"""Run all shipped example scripts under the current project interpreter.

This keeps example verification as a first-class repository workflow instead of
an ad-hoc manual step. The runner intentionally clears ``PYTHONPATH`` so
examples execute against the installed package contract, not a local path hack.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"


@dataclass(slots=True)
class ExampleFailure:
    """Captured example-run failure details."""

    path: Path
    returncode: int
    stderr: str


def _clean_env() -> dict[str, str]:
    """Return subprocess environment without legacy path overrides."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def _discover_examples(pattern: str) -> list[Path]:
    """Return runnable example scripts matching a glob pattern."""
    return sorted(
        path
        for path in EXAMPLES_DIR.glob(pattern)
        if path.is_file() and path.suffix == ".py"
    )


def _run_example(path: Path) -> ExampleFailure | None:
    """Execute one example script and return failure details if it fails."""
    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=REPO_ROOT,
        env=_clean_env(),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode == 0:
        return None

    stderr = result.stderr.strip() or result.stdout.strip()
    return ExampleFailure(path=path, returncode=result.returncode, stderr=stderr)


def main() -> int:
    """Run selected examples and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pattern",
        default="*.py",
        help="Glob pattern inside examples/ (default: %(default)s)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List matching examples without executing them.",
    )
    args = parser.parse_args()

    examples = _discover_examples(args.pattern)
    if not examples:
        print(f"[FAIL] No examples matched pattern: {args.pattern}")
        return 1

    if args.list:
        for path in examples:
            print(path.relative_to(REPO_ROOT))
        return 0

    failures: list[ExampleFailure] = []
    for path in examples:
        rel_path = path.relative_to(REPO_ROOT)
        print(f"[RUN] {rel_path}")
        failure = _run_example(path)
        if failure is not None:
            failures.append(failure)

    if failures:
        print("\n[FAIL] Example execution failures:")
        for failure in failures:
            rel_path = failure.path.relative_to(REPO_ROOT)
            print(f"  {rel_path} (exit {failure.returncode}): {failure.stderr}")
        return 1

    print(f"[PASS] Executed {len(examples)} example script(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
