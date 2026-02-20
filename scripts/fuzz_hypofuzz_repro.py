#!/usr/bin/env python3
"""Reproduce and document Hypothesis/HypoFuzz failures.

This tool helps reproduce Hypothesis property test failures and extract
@example decorators for regression testing.

NOTE: This script is for HYPOTHESIS/HYPOFUZZ failures only.
For Atheris crash files, use fuzz_atheris_repro.py instead.

How Hypothesis failures work:
- When a property test fails, Hypothesis shrinks to a minimal example
- The shrunk example is stored in .hypothesis/examples/<sha384_hash>
- On re-run, Hypothesis automatically replays the stored failure
- This script provides verbose output and @example extraction

Usage:
    uv run python scripts/fuzz_hypofuzz_repro.py tests/fuzz/test_syntax_parser_property.py
    uv run python scripts/fuzz_hypofuzz_repro.py \
        tests/fuzz/test_syntax_parser_property.py::test_roundtrip
    uv run python scripts/fuzz_hypofuzz_repro.py --verbose \
        tests/fuzz/test_syntax_parser_property.py::test_roundtrip
    uv run python scripts/fuzz_hypofuzz_repro.py --example \
        tests/fuzz/test_syntax_parser_property.py::test_roundtrip

Flags:
    --verbose   Show full pytest output with Hypothesis verbosity
    --example   Extract @example decorator from failure output
    --json      Output machine-readable JSON summary

JSON Output Format (--json):
    {
      "test_path": "tests/fuzz/test_syntax_parser_property.py::test_roundtrip",
      "status": "fail",
      "exit_code": 1,
      "timestamp": "2026-02-04T10:30:00+00:00",
      "error_type": "AssertionError",
      "traceback": "E   AssertionError: ...",
      "example": {"ftl": "msg = { $x", "args": "{}"},
      "example_decorator": "@example(ftl='msg = { $x')",
      "hypothesis_seed": 12345
    }

Exit Codes:
    0   Test passed (no failure to reproduce)
    1   Test failed (failure reproduced successfully)
    2   Error (test not found, import error, etc.)

Python 3.13+.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class ReproResult:
    """Result of reproduction attempt."""

    test_path: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    example_decorator: str | None = None
    error: str | None = None
    error_type: str | None = None
    traceback: str | None = None
    falsifying_example: dict[str, str] | None = None
    hypothesis_seed: int | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def parse_test_path(test_spec: str) -> tuple[str, str | None]:
    """Parse test specification into module and optional function.

    Args:
        test_spec: Test path like "tests/fuzz/test_syntax_parser_property.py::test_roundtrip"
            or "tests/fuzz/test_syntax_parser_property.py"

    Returns:
        Tuple of (module_name, function_name or None)
    """
    if "::" in test_spec:
        parts = test_spec.split("::", 1)
        return parts[0], parts[1]
    return test_spec, None


def build_pytest_path(module: str, function: str | None) -> str:
    """Build pytest path from module and function.

    Args:
        module: Module name or path (with or without .py extension).
            May be a bare name like "test_foo" or a full path like
            "tests/fuzz/test_syntax_parser_property.py".
        function: Optional function name

    Returns:
        Pytest path like "tests/fuzz/test_syntax_parser_property.py::test_roundtrip"
    """
    # Strip .py if present
    if module.endswith(".py"):
        module = module[:-3]

    # If already a rooted path (starts with tests/), use as-is; otherwise
    # assume a bare module name and prepend the tests/ root.
    path = f"{module}.py" if module.startswith("tests/") else f"tests/{module}.py"

    if function:
        path += f"::{function}"

    return path


def extract_falsifying_example(output: str) -> str | None:
    """Extract @example decorator from Hypothesis failure output.

    Hypothesis prints failures like:
        Falsifying example: test_roundtrip(
            ftl='...',
        )

    We parse this and convert to @example decorator format.

    Args:
        output: Combined stdout/stderr from pytest

    Returns:
        @example decorator string or None if not found
    """
    # Pattern matches "Falsifying example: test_name(" followed by arguments
    pattern = r"Falsifying example: \w+\(\s*\n((?:\s+\w+=.+,?\s*\n)+)\s*\)"
    match = re.search(pattern, output)

    if not match:
        # Try simpler single-line format
        pattern_simple = r"Falsifying example: \w+\((.+)\)"
        match_simple = re.search(pattern_simple, output)
        if match_simple:
            args = match_simple.group(1).strip()
            return f"@example({args})"
        return None

    # Parse multi-line arguments
    args_block = match.group(1)

    # Extract individual arguments
    args = []
    for raw_line in args_block.strip().split("\n"):
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#"):
            # Remove trailing comma
            if stripped.endswith(","):
                stripped = stripped[:-1]
            args.append(stripped)

    if not args:
        return None

    # Build @example decorator
    if len(args) == 1:
        return f"@example({args[0]})"
    return "@example(\n    " + ",\n    ".join(args) + ",\n)"


def extract_error_type(output: str) -> str | None:
    """Extract exception type from pytest failure output.

    Args:
        output: Combined stdout/stderr from pytest

    Returns:
        Exception class name (e.g., "AssertionError") or None
    """
    # Common pattern: "E   AssertionError: ..." or "E   ValueError: ..."
    pattern = r"E\s+(\w+Error|\w+Exception|\w+Warning):"
    match = re.search(pattern, output)
    if match:
        return match.group(1)

    # Alternative pattern from traceback: "raise AssertionError" or final line
    pattern_raise = r"(?:raise\s+)?(\w+Error|\w+Exception)\s*(?:\(|:)"
    match_raise = re.search(pattern_raise, output)
    if match_raise:
        return match_raise.group(1)

    return None


def extract_traceback(output: str) -> str | None:
    """Extract relevant traceback from pytest failure output.

    Args:
        output: Combined stdout/stderr from pytest

    Returns:
        Traceback string or None
    """
    # Find the traceback section
    lines = output.split("\n")
    traceback_lines: list[str] = []
    in_traceback = False

    for line in lines:
        # Start of traceback
        if "Traceback (most recent call last):" in line or line.strip().startswith("E "):
            in_traceback = True
        # Short form traceback markers
        if line.strip().startswith(">") or line.strip().startswith("E "):
            in_traceback = True
            traceback_lines.append(line)
            continue
        # End markers
        if in_traceback and (
            line.startswith(("===", "---")) or "passed" in line.lower()
        ):
            break
        if in_traceback:
            traceback_lines.append(line)

    if traceback_lines:
        # Limit to last 50 lines for readability
        return "\n".join(traceback_lines[-50:]).strip()
    return None


def extract_hypothesis_seed(output: str) -> int | None:
    """Extract Hypothesis random seed from output if available.

    Args:
        output: Combined stdout/stderr from pytest

    Returns:
        Seed integer or None
    """
    pattern = r"@seed\((\d+)\)"
    seed_match = re.search(pattern, output)
    if seed_match:
        return int(seed_match.group(1))

    # Alternative pattern: "Hypothesis random seed: 12345"
    pattern_alt = r"[Rr]andom seed[:\s]+(\d+)"
    match_alt = re.search(pattern_alt, output)
    if match_alt:
        return int(match_alt.group(1))

    return None


def extract_falsifying_example_dict(output: str) -> dict[str, str] | None:
    """Extract falsifying example as a dictionary for structured output.

    Args:
        output: Combined stdout/stderr from pytest

    Returns:
        Dictionary of argument names to string values, or None
    """
    # Pattern for multi-line format
    pattern = r"Falsifying example: \w+\(\s*\n((?:\s+\w+=.+,?\s*\n)+)\s*\)"
    match = re.search(pattern, output)

    if match:
        args_block = match.group(1)
        result: dict[str, str] = {}
        for raw_line in args_block.strip().split("\n"):
            stripped = raw_line.strip()
            if stripped and "=" in stripped:
                if stripped.endswith(","):
                    stripped = stripped[:-1]
                key, value = stripped.split("=", 1)
                result[key.strip()] = value.strip()
        return result if result else None

    # Try simpler single-line format
    pattern_simple = r"Falsifying example: \w+\((.+)\)"
    match_simple = re.search(pattern_simple, output)
    if match_simple:
        args_str = match_simple.group(1).strip()
        result = {}
        # Parse key=value pairs
        for pair in args_str.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                result[key.strip()] = value.strip()
        return result if result else None

    return None


def run_test(
    test_path: str,
    verbose: bool = False,
) -> ReproResult:
    """Run pytest on the specified test with Hypothesis verbosity.

    Args:
        test_path: Pytest path like "tests/test_foo.py::test_bar"
        verbose: Whether to use verbose Hypothesis output

    Returns:
        ReproResult with test outcome and output
    """
    # Check if test file exists
    test_file = test_path.split("::", maxsplit=1)[0]
    if not Path(test_file).exists():
        return ReproResult(
            test_path=test_path,
            passed=False,
            exit_code=2,
            stdout="",
            stderr="",
            error=f"Test file not found: {test_file}",
        )

    # Build pytest command
    cmd = ["uv", "run", "pytest", test_path, "-x", "-v", "--tb=short"]

    if verbose:
        cmd.append("--hypothesis-verbosity=verbose")

    # Run pytest (check=False: we inspect exit code ourselves)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
        check=False,
    )

    # Combine output for example extraction
    combined_output = result.stdout + "\n" + result.stderr

    # Extract failure details if test failed
    example_decorator = None
    error_type = None
    traceback = None
    falsifying_example = None
    hypothesis_seed = None

    if result.returncode != 0:
        example_decorator = extract_falsifying_example(combined_output)
        error_type = extract_error_type(combined_output)
        traceback = extract_traceback(combined_output)
        falsifying_example = extract_falsifying_example_dict(combined_output)
        hypothesis_seed = extract_hypothesis_seed(combined_output)

    return ReproResult(
        test_path=test_path,
        passed=result.returncode == 0,
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        example_decorator=example_decorator,
        error_type=error_type,
        traceback=traceback,
        falsifying_example=falsifying_example,
        hypothesis_seed=hypothesis_seed,
    )


def output_result(  # noqa: PLR0912, PLR0915
    result: ReproResult,
    use_json: bool,
    show_example: bool,
    verbose: bool,
) -> None:
    """Output the reproduction result.

    Args:
        result: ReproResult from test run
        use_json: Output JSON format
        show_example: Show @example decorator
        verbose: Show full output
    """
    if use_json:
        data: dict[str, str | int | dict[str, str] | None] = {
            "test_path": result.test_path,
            "status": "pass" if result.passed else "fail",
            "exit_code": result.exit_code,
            "timestamp": result.timestamp,
        }
        if result.error:
            data["error"] = result.error
        if result.error_type:
            data["error_type"] = result.error_type
        if result.traceback:
            data["traceback"] = result.traceback
        if result.falsifying_example:
            data["example"] = result.falsifying_example
        if result.example_decorator:
            data["example_decorator"] = result.example_decorator
        if result.hypothesis_seed is not None:
            data["hypothesis_seed"] = result.hypothesis_seed
        print(json.dumps(data, indent=2))
        return

    # Human-readable output
    if result.error:
        print(f"[ERROR] {result.error}")
        return

    if result.passed:
        print(f"[PASS] Test passed: {result.test_path}")
        print()
        print("No failure to reproduce. The test passes with current code.")
        print("If you expected a failure, check:")
        print("  1. Has the bug been fixed?")
        print("  2. Is the .hypothesis/examples/ database stale?")
        print("  3. Try: rm -rf .hypothesis && rerun the test")
        return

    print(f"[FAIL] Failure reproduced: {result.test_path}")
    print()

    if verbose:
        print("=" * 70)
        print("PYTEST OUTPUT")
        print("=" * 70)
        print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        print("=" * 70)
        print()

    if show_example and result.example_decorator:
        print("Add this decorator to your test function for regression:")
        print()
        print(result.example_decorator)
        print()
    elif show_example and not result.example_decorator:
        print("[WARN] Could not extract @example decorator from output.")
        print("Check the pytest output manually for the falsifying example.")
        print()

    print("Next steps:")
    print("  1. Investigate the failure in the test output above")
    print("  2. Fix the bug in the source code")
    print(f"  3. Re-run: uv run pytest {result.test_path} -x -v")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reproduce Hypothesis/HypoFuzz failures and generate regression tests.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reproduce a failing test with verbose output:
  uv run python scripts/fuzz_hypofuzz_repro.py --verbose \\
      tests/fuzz/test_syntax_parser_property.py::test_roundtrip

  # Extract @example decorator from failure:
  uv run python scripts/fuzz_hypofuzz_repro.py --example \\
      tests/fuzz/test_syntax_parser_property.py::test_roundtrip

  # Run all tests in a module:
  uv run python scripts/fuzz_hypofuzz_repro.py tests/fuzz/test_syntax_parser_property.py

  # JSON output for automation:
  uv run python scripts/fuzz_hypofuzz_repro.py --json \\
      tests/fuzz/test_syntax_parser_property.py::test_roundtrip
""",
    )
    parser.add_argument(
        "test",
        help="Test to reproduce (module::function or module)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show full pytest output with Hypothesis verbosity",
    )
    parser.add_argument(
        "--example",
        "-e",
        action="store_true",
        help="Extract @example decorator from failure output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON summary",
    )

    args = parser.parse_args()

    # Parse test path
    module, function = parse_test_path(args.test)
    test_path = build_pytest_path(module, function)

    # Run test
    result = run_test(
        test_path,
        verbose=args.verbose or args.example,
    )

    # Output result
    output_result(
        result,
        use_json=args.json,
        show_example=args.example,
        verbose=args.verbose,
    )

    # Exit code: 0 = pass, 1 = fail (reproduced), 2 = error
    if result.error:
        return 2
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
