#!/usr/bin/env python3
"""Run all shipped example scripts under the current project interpreter.

This keeps example verification as a first-class repository workflow instead of
an ad-hoc manual step. The runner intentionally clears ``PYTHONPATH`` so
examples execute against the installed package contract, validates a registered
stdout contract for every shipped example, and rejects unregistered example
scripts from silently bypassing semantic verification.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"


@dataclass(slots=True)
class ExampleFailure:
    """Captured example-run failure details."""

    path: Path
    returncode: int
    details: str


ExampleContract = Callable[[str], str | None]


def _require_output_markers(*markers: str) -> ExampleContract:
    """Build a validator that requires specific substrings in example stdout."""

    def _validator(stdout: str) -> str | None:
        missing = [marker for marker in markers if marker not in stdout]
        if not missing:
            return None
        return f"missing expected output marker(s): {', '.join(missing)}"

    return _validator


EXAMPLE_CONTRACTS: dict[str, ExampleContract] = {
    "benchmark_loaders.py": _require_output_markers("[OK] Benchmarks complete!"),
    "bidirectional_formatting.py": _require_output_markers("All examples completed!"),
    "custom_functions.py": _require_output_markers(
        "[SUCCESS] All custom function examples completed!"
    ),
    "ftl_linter.py": _require_output_markers(
        "[PASS] Clean FTL stays clean",
        "[PASS] Duplicate message IDs detected",
        "[PASS] Unknown functions detected",
        "[PASS] Undefined message references detected",
        "[PASS] Attribute-only messages flagged",
        "[PASS] Undefined term references detected",
        "[SUCCESS] Linter examples complete!",
    ),
    "ftl_transform.py": _require_output_markers("[SUCCESS] Transformer examples complete!"),
    "function_introspection.py": _require_output_markers(
        "[SUCCESS] All introspection examples completed!"
    ),
    "locale_fallback.py": _require_output_markers("[SUCCESS] All examples complete!"),
    "parser_only.py": _require_output_markers(
        "[PASS] Warning-only validation semantics verified",
        "[PASS] Invalid syntax semantics verified",
        "All examples completed successfully!",
    ),
    "property_based_testing.py": _require_output_markers(
        "ALL PROPERTY-BASED TESTS COMPLETED"
    ),
    "quickstart.py": _require_output_markers(
        "[SUCCESS] All examples completed successfully!"
    ),
    "thread_safety.py": _require_output_markers(
        "[SUCCESS] All thread safety examples complete!"
    ),
}


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
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        return ExampleFailure(path=path, returncode=result.returncode, details=stderr)

    validator = EXAMPLE_CONTRACTS.get(path.name)
    if validator is None:
        return ExampleFailure(
            path=path,
            returncode=1,
            details=f"no output contract registered for {path.name}",
        )

    contract_error = validator(result.stdout)
    if contract_error is None:
        return None

    return ExampleFailure(path=path, returncode=1, details=contract_error)


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
            print(f"  {rel_path} (exit {failure.returncode}): {failure.details}")
        return 1

    print(f"[PASS] Executed {len(examples)} example script(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
