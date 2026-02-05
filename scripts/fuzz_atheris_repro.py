#!/usr/bin/env python3
"""Reproduce and document Atheris fuzzer findings.

This tool closes the feedback loop for Atheris/libFuzzer crash discoveries:
1. Load crash/seed file (binary FTL or text FTL)
2. Parse through FluentParserV1 with full traceback
3. Generate @example decorator for regression test

NOTE: This script is for ATHERIS findings only (.fuzz_atheris_corpus/ crash files).
For Hypothesis/HypoFuzz failures, use fuzz_hypofuzz_repro.py instead.

Usage:
    uv run python scripts/fuzz_atheris_repro.py .fuzz_atheris_corpus/crash_xxx
    uv run python scripts/fuzz_atheris_repro.py --example .fuzz_atheris_corpus/crash_xxx
    uv run python scripts/fuzz_atheris_repro.py --json .fuzz_atheris_corpus/crash_xxx
    uv run python scripts/fuzz_atheris_repro.py --verbose fuzz_atheris/seeds/valid_message.ftl

Flags:
    --example   Output @example decorator for copy-paste into test file
    --json      Output machine-readable JSON summary (for automation)
    --verbose   Show parsed AST on success

Exit Codes:
    0   Parsed successfully (no crash)
    1   Parser crashed (finding confirmed)
    2   File read error

Python 3.13+.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ftllexengine.syntax.ast import Resource

# Maximum input size (10 MB) - prevents memory exhaustion from malicious inputs
MAX_INPUT_SIZE = 10 * 1024 * 1024


@dataclass
class ReadResult:
    """Result of reading and decoding a file."""

    source: str
    has_invalid_utf8: bool
    error: str | None = None
    exit_code: int = 0


def read_and_decode_file(file_path: Path, use_json: bool) -> ReadResult:
    """Read file and decode to string.

    Returns:
        ReadResult with source text or error information.
    """
    if not file_path.exists():
        if use_json:
            error = json.dumps({
                "result": "error", "error": "file_not_found", "file": str(file_path)
            })
        else:
            error = f"[ERROR] File not found: {file_path}"
        return ReadResult(source="", has_invalid_utf8=False, error=error, exit_code=2)

    try:
        data = file_path.read_bytes()
    except OSError as e:
        if use_json:
            error = json.dumps({
                "result": "error",
                "error": "read_error",
                "file": str(file_path),
                "message": str(e),
            })
        else:
            error = f"[ERROR] Cannot read file: {e}"
        return ReadResult(source="", has_invalid_utf8=False, error=error, exit_code=2)

    # Check size limit to prevent memory exhaustion
    if len(data) > MAX_INPUT_SIZE:
        if use_json:
            error = json.dumps({
                "result": "error",
                "error": "file_too_large",
                "file": str(file_path),
                "size": len(data),
                "max_size": MAX_INPUT_SIZE,
            })
        else:
            size_mb = len(data) / (1024 * 1024)
            error = f"[ERROR] File too large: {size_mb:.1f} MB (max: 10 MB)"
        return ReadResult(source="", has_invalid_utf8=False, error=error, exit_code=2)

    # Decode to string using surrogateescape (PEP 383) for invalid UTF-8
    has_invalid_utf8 = False
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        source = data.decode("utf-8", errors="surrogateescape")
        has_invalid_utf8 = True

    return ReadResult(source=source, has_invalid_utf8=has_invalid_utf8)


def output_example(source: str) -> None:
    """Output @example decorator for copy-paste into test file."""
    escaped = repr(source)
    print("# Add this decorator to your test function:")
    print(f"@example(ftl={escaped})")
    print()
    print("# Or for hypothesis strategies:")
    print(f"@example({escaped})")


def output_finding(
    file_path: Path,
    source: str,
    has_invalid_utf8: bool,
    exc: BaseException,
    use_json: bool,
) -> None:
    """Output crash finding information."""
    if use_json:
        print(json.dumps({
            "result": "finding",
            "file": str(file_path),
            "input_length": len(source),
            "has_invalid_utf8": has_invalid_utf8,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "example_decorator": f"@example(ftl={source!r})",
        }))
    else:
        print(f"[FINDING] Parser crashed with {type(exc).__name__}: {exc}")
        print()
        print("Full traceback:")
        print("-" * 60)
        traceback.print_exc()
        print("-" * 60)
        print()
        print("Next steps:")
        print("  1. Add @example decorator to preserve this case:")
        escaped = repr(source)
        print(f"     @example(ftl={escaped})")
        print("  2. Fix the bug in the parser")
        print("  3. Run: uv run scripts/fuzz.sh (to verify fix)")


def output_success(
    file_path: Path,
    source: str,
    has_invalid_utf8: bool,
    result: Resource,
    use_json: bool,
    verbose: bool,
) -> None:
    """Output successful parse result."""
    entry_count = len(result.entries)
    message_count = sum(
        1 for e in result.entries if hasattr(e, "id") and hasattr(e, "value")
    )

    if use_json:
        print(json.dumps({
            "result": "pass",
            "file": str(file_path),
            "input_length": len(source),
            "has_invalid_utf8": has_invalid_utf8,
            "entry_count": entry_count,
            "message_count": message_count,
        }))
    else:
        print("[OK] Parsed successfully")
        print(f"     Entries: {entry_count}")
        print(f"     Messages/Terms: {message_count}")

        if verbose:
            print()
            print("Parsed AST:")
            print("-" * 60)
            for i, entry in enumerate(result.entries):
                entry_type = type(entry).__name__
                if hasattr(entry, "id"):
                    print(f"  [{i}] {entry_type}: {entry.id.name}")
                else:
                    print(f"  [{i}] {entry_type}")
            print("-" * 60)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reproduce fuzzer findings and generate regression tests.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reproduce a crash and see full traceback:
  uv run python scripts/fuzz_atheris_repro.py .fuzz_atheris_corpus/crash_xxx

  # Generate @example decorator for test file:
  uv run python scripts/fuzz_atheris_repro.py --example .fuzz_atheris_corpus/crash_xxx

  # Verify a seed file parses correctly:
  uv run python scripts/fuzz_atheris_repro.py fuzz_atheris/seeds/complex.ftl
""",
    )
    parser.add_argument("file", type=Path, help="Crash file or FTL seed to reproduce")
    parser.add_argument(
        "--example",
        action="store_true",
        help="Output @example decorator for copy-paste into test file",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show parsed AST on success"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON summary (for automation)",
    )
    args = parser.parse_args()

    # Read and decode file
    read_result = read_and_decode_file(args.file, args.json)
    if read_result.error:
        if args.json:
            print(read_result.error)
        else:
            print(read_result.error, file=sys.stderr)
        return read_result.exit_code

    source = read_result.source
    has_invalid_utf8 = read_result.has_invalid_utf8

    if has_invalid_utf8 and not args.json:
        print("[WARN] File contains invalid UTF-8, using surrogateescape")

    # Output @example decorator if requested
    if args.example:
        output_example(source)
        return 0

    # Import parser (inside function to avoid import errors if package broken)
    try:
        from ftllexengine.syntax.parser import (  # noqa: PLC0415  # pylint: disable=C0415
            FluentParserV1,
        )
    except ImportError as e:
        if args.json:
            print(json.dumps({
                "result": "error", "error": "import_error", "message": str(e)
            }))
        else:
            print(f"[ERROR] Cannot import FluentParserV1: {e}", file=sys.stderr)
        return 2

    # Log info for non-JSON output
    if not args.json:
        print(f"[INFO] Reproducing: {args.file}")
        print(f"[INFO] Input length: {len(source)} chars")
        print(f"[INFO] Input preview: {source[:100]!r}...")
        print()

    # Attempt parse
    p = FluentParserV1()

    try:
        result = p.parse(source)
    except (ValueError, TypeError, AttributeError, KeyError, IndexError) as e:
        output_finding(args.file, source, has_invalid_utf8, e, args.json)
        return 1

    output_success(args.file, source, has_invalid_utf8, result, args.json, args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
