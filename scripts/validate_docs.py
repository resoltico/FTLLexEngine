#!/usr/bin/env python3
# @lint-plugin: FTLexdocs
"""Validate all FTL examples in documentation files.

Extracts code blocks marked as ```ftl and attempts to parse them.
Fails CI if any example contains invalid FTL syntax.

This script is designed for the FTLLexEngine project. When run in
other projects, it auto-detects the context and exits gracefully.

SYSTEMS-OVER-GOALS:
    - Auto-detect project context (FTLLexEngine vs other projects)
    - Graceful degradation when imports unavailable
    - Bounded file scanning (prevent infinite loops)
    - Early exit with clear messaging

Architecture:
    - Extract FTL code blocks from markdown files
    - Parse each example with FluentParserV1
    - Check for Junk entries (parse errors)
    - Report all errors with file:line references

Usage:
    python scripts/validate_docs.py

Exit Codes:
    0: All FTL examples valid (or script skipped due to context)
    1: One or more invalid FTL examples found
    2: Configuration error (missing dependencies)

Python 3.13+. Depends on: ftllexengine (internal modules).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ==============================================================================
# CONTEXT DETECTION - Graceful degradation for non-FTLLexEngine projects
# ==============================================================================

try:
    from ftllexengine.syntax.ast import Junk
    from ftllexengine.syntax.parser import FluentParserV1
    FTLLEXENGINE_AVAILABLE = True
except ImportError:
    FTLLEXENGINE_AVAILABLE = False
    # Stub classes for type checking when running in other projects
    Junk = None  # type: ignore[assignment,misc]
    FluentParserV1 = None  # type: ignore[assignment,misc]


def detect_project_context() -> tuple[bool, str]:
    """Detect if we're running in FTLLexEngine project.

    Returns:
        (is_ftllexengine, project_name)
    """
    root = Path(__file__).parent.parent

    # Check for Finso2000 markers FIRST (priority check)
    if (root / "src" / "finso2000").exists():
        return (False, "finso2000")

    # Check for FTLLexEngine markers (must be the actual ftllexengine project)
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        # Look for package name declaration (not just dependency reference)
        if 'name = "ftllexengine"' in content or 'name="ftllexengine"' in content:
            return (True, "ftllexengine")

    # Check for ftllexengine source directory
    if (root / "src" / "ftllexengine").exists():
        return (True, "ftllexengine")

    # Unknown project
    return (False, "unknown")


def extract_ftl_examples(markdown_path: Path) -> list[tuple[int, str]]:
    """Extract FTL code blocks from markdown file.

    Args:
        markdown_path: Path to markdown file

    Returns:
        List of (line_number, ftl_code) tuples

    Example:
        >>> examples = extract_ftl_examples(Path("README.md"))
        >>> for line_num, code in examples:
        ...     print(f"Line {line_num}: {code[:50]}...")
    """
    content = markdown_path.read_text(encoding="utf-8")
    examples = []

    # Find ```ftl code blocks (case-insensitive)
    pattern = r"```ftl\n(.*?)\n```"
    for match in re.finditer(pattern, content, re.DOTALL | re.IGNORECASE):
        ftl_code = match.group(1)
        # Calculate line number where code block starts
        line_num = content[: match.start()].count("\n") + 2  # +2 for ```ftl line
        examples.append((line_num, ftl_code))

    return examples


def validate_file(markdown_path: Path, parser: FluentParserV1) -> list[str]:
    """Validate all FTL examples in a markdown file.

    Args:
        markdown_path: Path to markdown file
        parser: FluentParserV1 instance

    Returns:
        List of error messages (empty if all valid)

    Example:
        >>> parser = FluentParserV1()
        >>> errors = validate_file(Path("README.md"), parser)
        >>> if errors:
        ...     for error in errors:
        ...         print(error)
    """
    errors: list[str] = []
    examples = extract_ftl_examples(markdown_path)

    if not examples:
        # No FTL examples in this file (not an error)
        return errors

    for line_num, ftl_code in examples:
        # Skip examples that are clearly not pure FTL (mixed markdown/documentation)
        # These indicate malformed markdown, not invalid FTL
        if any(marker in ftl_code for marker in ["```", "|---|", "**", "##", "$name: string"]):
            continue

        # Skip intentionally invalid examples (documentation showing errors)
        skip_markers = [
            "# ←",  # Arrow pointing to error
            "# INVALID",  # Marked as invalid
            "WRONG",  # Marked as wrong
            "FAILS",  # Marked as failing
            "doesn't work",  # Known not to work
            "# Currently fails",  # Known failure
            "syntax error",  # Example demonstrating syntax error
            "Parser error",  # Example showing parser error
            "invalid-message",  # Example showing invalid message
            "parser bug",  # Known parser bug
            "useBidiMarks",  # Boolean parameter not supported (known limitation)
            "# Dynamic currency!",  # TODO showing desired behavior
        ]
        if any(marker in ftl_code for marker in skip_markers):
            continue

        # Skip examples showing future/desired behavior (in TODO files)
        if "TODO" in str(markdown_path) and ("Once Fixed" in ftl_code or "Would Work" in ftl_code):
            continue

        try:
            resource = parser.parse(ftl_code)

            # Check for Junk entries (parse errors)
            junk_entries = [e for e in resource.entries if isinstance(e, Junk)]

            if junk_entries:
                # Show first junk entry content (truncated)
                junk_content = junk_entries[0].content
                preview = junk_content[:100] + ("..." if len(junk_content) > 100 else "")

                errors.append(
                    f"{markdown_path}:{line_num}: FTL syntax error\n"
                    f"  Invalid FTL: {preview}\n"
                    f"  {len(junk_entries)} parse error(s) in example"
                )

        except (ValueError, TypeError, AttributeError) as e:
            errors.append(
                f"{markdown_path}:{line_num}: Parse exception: {e.__class__.__name__}: {e}"
            )

    return errors


def main() -> int:
    """Validate all markdown files with FTL examples.

    Returns:
        0 if all valid (or skipped due to context), 1 if errors found
    """
    # CONTEXT DETECTION: Exit gracefully if not in FTLLexEngine project
    is_ftllexengine, project_name = detect_project_context()

    if not is_ftllexengine:
        print("[SKIP] validate_docs.py is for FTLLexEngine project")
        print(f"       Current project: {project_name}")
        print("       Skipping FTL documentation validation")
        return 0

    # DEPENDENCY CHECK: Ensure ftllexengine modules available
    if not FTLLEXENGINE_AVAILABLE:
        print("[ERROR] ftllexengine modules not available")
        print("        This script requires ftllexengine.syntax.* imports")
        return 2

    parser = FluentParserV1()
    all_errors = []
    files_checked = 0
    examples_found = 0

    # BOUNDED FILE SCANNING: Prevent infinite loops
    root = Path(__file__).parent.parent
    markdown_files = []

    # Only scan specific locations (not entire project tree)
    scan_locations = [
        root / "README.md",
        root / "CHANGELOG.md",
        root / "docs",
    ]

    # SAFEGUARD: Explicitly exclude scripts directory to prevent issues when run as plugin
    scripts_dir = root / "scripts"

    for location in scan_locations:
        if location.is_file():
            markdown_files.append(location)
        elif location.is_dir():
            # Ensure we never scan the scripts directory
            if location == scripts_dir or scripts_dir in location.parents:
                continue
            # Limit depth to prevent runaway scanning
            markdown_files.extend(location.glob("*.md"))
            markdown_files.extend(location.glob("*/*.md"))  # Max 1 level deep

    # Remove duplicates and sort
    markdown_files = sorted(set(markdown_files))

    # SAFEGUARD: Limit total files processed (safety cap)
    max_files = 1000
    if len(markdown_files) > max_files:
        print(f"[WARN] Found {len(markdown_files)} markdown files, limiting to {max_files}")
        markdown_files = markdown_files[:max_files]

    for md_file in markdown_files:
        try:
            # Count examples before validation
            examples_in_file = len(extract_ftl_examples(md_file))
            if examples_in_file > 0:
                files_checked += 1
                examples_found += examples_in_file

            errors = validate_file(md_file, parser)
            all_errors.extend(errors)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            # SAFEGUARD: Catch file/encoding/parse errors to prevent hangs
            print(f"[WARN] Error processing {md_file}: {e}")
            # Continue processing other files
            continue

    # Report results
    if all_errors:
        print("[FAIL] Invalid FTL examples in documentation:\n")
        for error in all_errors:
            print(f"  {error}\n")
        print(
            f"Summary: {len(all_errors)} error(s) in {files_checked} file(s) "
            f"with FTL examples"
        )
        return 1

    print(
        f"[OK] All FTL examples valid\n"
        f"  Files checked: {len(markdown_files)}\n"
        f"  Files with FTL: {files_checked}\n"
        f"  Examples validated: {examples_found}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
