#!/usr/bin/env python3
"""Replay a fuzzer finding artifact to confirm reproducibility.

Reads a finding source .ftl file (written by a fuzzer's _write_finding_artifact),
runs the parse-serialize-reparse cycle using the production parser/serializer,
and reports whether the finding reproduces WITHOUT Atheris instrumentation.

This script runs in the main project venv (not .venv-atheris). If a finding
reproduces here, it is a real parser/serializer bug. If it does NOT reproduce,
it may be an Atheris str-hook instrumentation artifact.

Usage:
    python fuzz_atheris/fuzz_atheris_replay_finding.py \\
        .fuzz_atheris_corpus/structured/findings/finding_0001_source.ftl
    python fuzz_atheris/fuzz_atheris_replay_finding.py \\
        .fuzz_atheris_corpus/structured/findings/  # replay all

Exit codes:
    0 - No findings reproduced (or no files given)
    1 - At least one finding reproduced (real bug confirmed)
"""

from __future__ import annotations

import difflib
import json
import pathlib
import sys

from ftllexengine.syntax.ast import Junk
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import FluentSerializer


def replay_source(source: str, label: str) -> bool:
    """Run roundtrip on source, return True if finding reproduces."""
    parser = FluentParserV1()
    serializer = FluentSerializer()

    ast1 = parser.parse(source)
    if any(isinstance(e, Junk) for e in ast1.entries):
        print(f"  [{label}] Parse produced Junk -- cannot verify roundtrip")
        return False

    s1 = serializer.serialize(ast1)
    ast2 = parser.parse(s1)

    if any(isinstance(e, Junk) for e in ast2.entries):
        print(f"  [{label}] [CONFIRMED] S1 produces Junk on re-parse")
        print(f"    S1: {s1[:300]!r}")
        return True

    s2 = serializer.serialize(ast2)

    if s1 != s2:
        print(f"  [{label}] [CONFIRMED] Convergence failure: S1 != S2")
        print(f"    S1 ({len(s1)} chars): {s1[:200]!r}")
        print(f"    S2 ({len(s2)} chars): {s2[:200]!r}")
        print()

        # Unified diff
        diff = difflib.unified_diff(
            s1.splitlines(keepends=True),
            s2.splitlines(keepends=True),
            fromfile="S1 (serialize(parse(source)))",
            tofile="S2 (serialize(parse(S1)))",
            lineterm="",
        )
        diff_lines = list(diff)
        if diff_lines:
            print("    --- Diff ---")
            for line in diff_lines[:30]:
                print(f"    {line}")
            if len(diff_lines) > 30:
                print(f"    ... ({len(diff_lines) - 30} more lines)")
        return True

    print(f"  [{label}] Not reproduced (S1 == S2)")
    return False


def replay_file(path: pathlib.Path) -> bool:
    """Replay a single finding source file."""
    source = path.read_text(encoding="utf-8")
    label = path.name

    # Also load metadata if available
    meta_path = path.with_name(path.name.replace("_source.ftl", "_meta.json"))
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            print(f"  Metadata: pattern={meta.get('pattern')}, "
                  f"iteration={meta.get('iteration')}, "
                  f"diff_offset={meta.get('diff_offset')}")
        except (json.JSONDecodeError, OSError):
            pass

    return replay_source(source, label)


def main() -> int:
    """Entry point."""
    if len(sys.argv) < 2:
        print("Usage: python fuzz_atheris/fuzz_atheris_replay_finding.py "
              "<source.ftl | findings_dir/>")
        return 0

    target = pathlib.Path(sys.argv[1])
    any_reproduced = False

    if target.is_dir():
        # Replay all *_source.ftl files in the directory
        sources = sorted(target.glob("*_source.ftl"))
        if not sources:
            print(f"No *_source.ftl files found in {target}")
            return 0

        print(f"Replaying {len(sources)} finding(s) from {target}")
        print()
        for src_file in sources:
            if replay_file(src_file):
                any_reproduced = True
            print()
    elif target.is_file():
        print(f"Replaying {target}")
        print()
        if replay_file(target):
            any_reproduced = True
    else:
        print(f"Path not found: {target}", file=sys.stderr)
        return 1

    print()
    if any_reproduced:
        print("[RESULT] At least one finding REPRODUCED without Atheris (real bug)")
        return 1

    print("[RESULT] No findings reproduced without Atheris")
    print("         Possible causes: Atheris str-hook instrumentation artifact,")
    print("         or non-deterministic behavior during the original fuzzing run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
