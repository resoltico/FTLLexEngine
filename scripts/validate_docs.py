#!/usr/bin/env python3
# @lint-plugin: DocValidator
"""Validate code examples in documentation files against project parsers.

Ensures that documentation never "lies" by verifying that every code block
marked with a specific language (e.g., ```ftl) is syntactically valid according
to the actual project parser.

PHILOSOPHY:
    Documentation is the interface of your code. If the examples in your
    README.md are syntactically invalid, the documentation is broken.
    This script treats documentation as testable code, enforcing
    correctness at build time.

SYSTEMS-OVER-GOALS:
    - Zero-Configuration Discovery: Reads [tool.validate-docs] from pyproject.toml.
    - Intentionality: Support "Skip Markers" for documenting known errors.
    - CI Optimized: Emits JSON and concise terminal feedback.
    - Universal: Works for any project with a python-accessible parser.

ARCHITECTURE:
    - tomllib (Python 3.11+ stdlib) for configuration.
    - importlib for dynamic parser instantiation.
    - pathlib for robust file I/O.

EXIT CODES:
    0: All examples valid (or skipped).
    1: One or more invalid examples found.
    2: Configuration or import error.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

try:
    from ftllexengine.syntax.ast import Junk
except ImportError:
    Junk = None  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class CheckConfig:
    """Configuration for documentation validation."""

    project_name: str
    scan_globs: list[str]
    skip_markers: list[str]
    parser_path: str
    language: str = "ftl"

    @classmethod
    def from_pyproject(cls, root: Path) -> Self:
        """Load configuration from pyproject.toml."""
        toml_path = root / "pyproject.toml"
        if not toml_path.exists():
            return cls(
                project_name="Unknown",
                scan_globs=["README.md", "CHANGELOG.md", "docs/**/*.md"],
                skip_markers=[],
                parser_path="",
            )

        with toml_path.open("rb") as f:
            data = tomllib.load(f)

        project_name = data.get("project", {}).get("name", "Unknown").capitalize()
        config = data.get("tool", {}).get("validate-docs", {})

        return cls(
            project_name=project_name,
            scan_globs=config.get("scan_globs", ["README.md", "CHANGELOG.md", "docs/**/*.md"]),
            skip_markers=config.get("skip_markers", []),
            parser_path=config.get("parser_path", ""),
            language=config.get("language", "ftl"),
        )


@dataclass
class ExampleFailure:
    """Details of a failed documentation example validation."""

    file: str
    line: int
    content: str
    error: str
    error_type: str = "SyntaxError"


@dataclass
class ValidationReport:
    """Summary of the validation run."""

    status: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    files_checked: int = 0
    examples_validated: int = 0
    failures: list[ExampleFailure] = field(default_factory=list)

    def to_json(self) -> str:
        """Return JSON representation of the report."""
        return json.dumps(
            {
                "status": self.status,
                "timestamp": self.timestamp,
                "metrics": {
                    "files_checked": self.files_checked,
                    "examples_validated": self.examples_validated,
                    "failure_count": len(self.failures),
                },
                "failures": [
                    {
                        "file": f.file,
                        "line": f.line,
                        "error_type": f.error_type,
                        "message": f.error,
                        "snippet": f.content[:100] + "...",
                    }
                    for f in self.failures
                ],
            },
            indent=2,
        )


def get_parser(path: str) -> Any:
    """Instantiate a parser from a string path (module.submodule:ClassName)."""
    if not path or ":" not in path:
        return None

    try:
        module_path, class_name = path.split(":", 1)
        module = importlib.import_module(module_path)
        parser_cls = getattr(module, class_name)
        return parser_cls()
    except (ImportError, AttributeError) as e:
        print(f"[ERROR] Could not load parser {path!r}: {e!s}", file=sys.stderr)
        return None


def validate_code(code: str, parser: Any) -> str | None:
    """Validate a code block using the provided parser.

    Returns an error message if invalid, else None.
    Handles 'ftllexengine' AST 'Junk' objects specifically.
    """
    try:
        # Standard Fluent parser interface: .parse(text) returns a Resource
        resource = parser.parse(code)

        # Performance: Search for Junk entries if it's an ftllexengine/fluent resource
        if Junk is not None and hasattr(resource, "entries"):
            junk = [e for e in resource.entries if isinstance(e, Junk)]
            if junk:
                return f"FTL Parsing failed: {junk[0].content[:100]}"
    except (ValueError, TypeError, AttributeError, ImportError) as e:
        return f"{e.__class__.__name__}: {e!s}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Architecture: We catch Exception here because validate_docs is a universal
        # runner that interacts with arbitrary third-party parsers. A crash in a
        # parser must not crash the entire validation suite; instead, we report
        # it as a failed example to keep the feedback loop intact for the agent.
        return f"UnexpectedError: {e!s}"

    return None


def discover_files(root: Path, globs: list[str]) -> list[Path]:
    """Find all markdown files matching the provides globs."""
    markdown_files: list[Path] = []
    for pattern in globs:
        markdown_files.extend(root.glob(pattern))
    return sorted(set(markdown_files))


def process_file(
    md_file: Path,
    root: Path,
    config: CheckConfig,
    parser: Any,
    report: ValidationReport,
    pattern: re.Pattern[str],
) -> None:
    """Extract and validate all examples within a single markdown file."""
    try:
        content = md_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    report.files_checked += 1
    rel_path = str(md_file.relative_to(root))

    for match in pattern.finditer(content):
        indent = match.group(1)
        language = match.group(2).lower()
        code_block = match.group(3)

        if language != config.language:
            continue

        report.examples_validated += 1

        # Dedent the code block if the fence was indented
        if indent:
            lines = code_block.split("\n")
            dedented = [line.removeprefix(indent) for line in lines]
            code_block = "\n".join(dedented)

        # Skip intentional errors
        if any(m in code_block for m in config.skip_markers):
            continue

        error = validate_code(code_block, parser)
        if error:
            line_num = content[: match.start()].count("\n") + 2
            report.failures.append(
                ExampleFailure(file=rel_path, line=line_num, content=code_block, error=error)
            )


def main() -> int:
    """Main entry point."""
    root = Path(__file__).parent.parent
    config = CheckConfig.from_pyproject(root)

    print(f"=== {config.project_name} Documentation Validation ===")

    if not config.parser_path:
        print("[SKIP] No parser_path defined in pyproject.toml [tool.validate-docs]")
        return 0

    parser = get_parser(config.parser_path)
    if not parser:
        return 2

    report = ValidationReport(status="pass")
    markdown_files = discover_files(root, config.scan_globs)

    block_pattern = re.compile(
        r"^([ \t]*)```(\S+)\n(.*?)\n\1```", re.DOTALL | re.MULTILINE | re.IGNORECASE
    )

    for md_file in markdown_files:
        process_file(md_file, root, config, parser, report, block_pattern)

    if report.failures:
        report.status = "fail"
        print("\n[FAIL] Found validation errors in documentation:")
        for f in report.failures:
            print(f"  {f.file}:{f.line}: {f.error}")

        print("\n[SUMMARY-JSON-BEGIN]")
        print(report.to_json())
        print("[SUMMARY-JSON-END]")
        return 1

    msg = (
        f"[PASS] {report.examples_validated} examples validated "
        f"across {report.files_checked} files."
    )
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
