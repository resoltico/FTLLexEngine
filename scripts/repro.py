#!/usr/bin/env python3
"""Reproduce and document fuzzer findings.

This tool closes the feedback loop for fuzzing discoveries:
1. Load crash/seed file (binary or text)
2. Parse through FluentParserV1 with full traceback
3. Generate @example decorator for regression test

Usage:
    uv run python scripts/repro.py .fuzz_corpus/crash_xxx
    uv run python scripts/repro.py --example .fuzz_corpus/crash_xxx
    uv run python scripts/repro.py --json .fuzz_corpus/crash_xxx
    uv run python scripts/repro.py --verbose fuzz/seeds/valid_message.ftl

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
from pathlib import Path

# Maximum input size (10 MB) - prevents memory exhaustion from malicious inputs
MAX_INPUT_SIZE = 10 * 1024 * 1024


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
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON summary (for automation)",
    )
    args = parser.parse_args()

    # Read file
    file_path: Path = args.file
    if not file_path.exists():
        if args.json:
            print(json.dumps({"result": "error", "error": "file_not_found", "file": str(file_path)}))
        else:
            print(f"[ERROR] File not found: {file_path}", file=sys.stderr)
        return 2

    try:
        data = file_path.read_bytes()
    except OSError as e:
        if args.json:
            print(json.dumps({"result": "error", "error": "read_error", "file": str(file_path), "message": str(e)}))
        else:
            print(f"[ERROR] Cannot read file: {e}", file=sys.stderr)
        return 2

    # Check size limit to prevent memory exhaustion
    if len(data) > MAX_INPUT_SIZE:
        if args.json:
            print(json.dumps({
                "result": "error",
                "error": "file_too_large",
                "file": str(file_path),
                "size": len(data),
                "max_size": MAX_INPUT_SIZE,
            }))
        else:
            size_mb = len(data) / (1024 * 1024)
            print(f"[ERROR] File too large: {size_mb:.1f} MB (max: 10 MB)", file=sys.stderr)
        return 2

    # Decode to string
    has_invalid_utf8 = False
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        source = data.decode("utf-8", errors="replace")
        has_invalid_utf8 = True
        if not args.json:
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
        if args.json:
            print(json.dumps({"result": "error", "error": "import_error", "message": str(e)}))
        else:
            print(f"[ERROR] Cannot import FluentParserV1: {e}", file=sys.stderr)
        return 2

    # Attempt parse
    if not args.json:
        print(f"[INFO] Reproducing: {file_path}")
        print(f"[INFO] Input length: {len(source)} chars")
        print(f"[INFO] Input preview: {source[:100]!r}...")
        print()

    p = FluentParserV1()

    try:
        result = p.parse(source)
    except Exception as e:
        if args.json:
            print(json.dumps({
                "result": "finding",
                "file": str(file_path),
                "input_length": len(source),
                "has_invalid_utf8": has_invalid_utf8,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
                "example_decorator": f"@example(ftl={repr(source)})",
            }))
        else:
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

    if args.json:
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
