#!/usr/bin/env python3
"""Reproduce and document fuzzer findings.

This tool closes the feedback loop for fuzzing discoveries:
1. Load crash/seed file (binary or text)
2. Parse through FluentParserV1 with full traceback
3. Generate @example decorator for regression test

Usage:
    uv run python scripts/repro.py .fuzz_corpus/crash_xxx
    uv run python scripts/repro.py --example .fuzz_corpus/crash_xxx
    uv run python scripts/repro.py fuzz/seeds/valid_message.ftl

Exit Codes:
    0   Parsed successfully (no crash)
    1   Parser crashed (finding confirmed)
    2   File read error

Python 3.13+.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reproduce fuzzer findings and generate regression tests.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reproduce a crash and see full traceback:
  uv run python scripts/repro.py .fuzz_corpus/crash_xxx

  # Generate @example decorator for test file:
  uv run python scripts/repro.py --example .fuzz_corpus/crash_xxx

  # Verify a seed file parses correctly:
  uv run python scripts/repro.py fuzz/seeds/complex.ftl
""",
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Crash file or FTL seed to reproduce",
    )
    parser.add_argument(
        "--example",
        action="store_true",
        help="Output @example decorator for copy-paste into test file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show parsed AST on success",
    )
    args = parser.parse_args()

    # Read file
    file_path: Path = args.file
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}", file=sys.stderr)
        return 2

    try:
        data = file_path.read_bytes()
    except OSError as e:
        print(f"[ERROR] Cannot read file: {e}", file=sys.stderr)
        return 2

    # Decode to string
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        source = data.decode("utf-8", errors="replace")
        print("[WARN] File contains invalid UTF-8, using replacement chars")

    # Output @example decorator if requested
    if args.example:
        # Escape for Python string literal
        escaped = repr(source)
        print("# Add this decorator to your test function:")
        print(f"@example(ftl={escaped})")
        print()
        print("# Or for hypothesis strategies:")
        print(f"@example({escaped})")
        return 0

    # Import parser (inside function to avoid import errors if package broken)
    try:
        from ftllexengine.syntax.parser import FluentParserV1
    except ImportError as e:
        print(f"[ERROR] Cannot import FluentParserV1: {e}", file=sys.stderr)
        return 2

    # Attempt parse
    print(f"[INFO] Reproducing: {file_path}")
    print(f"[INFO] Input length: {len(source)} chars")
    print(f"[INFO] Input preview: {source[:100]!r}...")
    print()

    p = FluentParserV1()

    try:
        result = p.parse(source)
    except Exception as e:
        print(f"[FINDING] Parser crashed with {type(e).__name__}: {e}")
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
        return 1

    # Success
    entry_count = len(result.entries)
    message_count = sum(
        1 for e in result.entries if hasattr(e, "id") and hasattr(e, "value")
    )

    print(f"[OK] Parsed successfully")
    print(f"     Entries: {entry_count}")
    print(f"     Messages/Terms: {message_count}")

    if args.verbose:
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
