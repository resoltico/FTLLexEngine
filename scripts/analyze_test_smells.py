#!/usr/bin/env python3
"""Universal test smell analyzer for Python test suites.

Detects anti-patterns and code smells in test files. Designed to work with
any Python project using pytest, unittest, or Hypothesis.

Architecture:
    - Single-pass AST walking with multi-check statistics collection
    - Modular rule-based detection system
    - Severity-prioritized reporting with multiple output modes
    - CI-friendly JSON and SARIF output options
    - Configurable via pyproject.toml [tool.test-smells]
    - Inline suppression via # noqa: test-smell[rule-name]

Exit Codes:
    0: No critical smells found
    1: Critical smells detected (with --fail-on-critical)
    2: Configuration error

Python 3.13+. Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final

if TYPE_CHECKING:
    from collections.abc import Sequence


# =============================================================================
# CONSTANTS
# =============================================================================

ASSERTION_OVERLOAD_THRESHOLD: Final[int] = 10
MOCK_OVERUSE_THRESHOLD: Final[int] = 5
MIN_TEST_NAME_LENGTH: Final[int] = 12  # "test_" (5) + meaningful name (7+)
MAGIC_NUMBER_THRESHOLD: Final[int] = 100

# Exact match patterns (test name must be exactly this)
GENERIC_TEST_EXACT: Final[frozenset[str]] = frozenset({
    "test_it",
    "test_1",
    "test_2",
    "test_foo",
    "test_bar",
})

# Prefix patterns (test name starts with these followed by numbers or nothing meaningful)
# Note: "test_basic_" removed - "basic" is a valid descriptor (basic vs advanced tests)
GENERIC_TEST_PREFIXES: Final[tuple[str, ...]] = (
    "test_case_",
    "test_test_",
)

HYPOTHESIS_DECORATORS: Final[frozenset[str]] = frozenset({"given", "settings", "example"})

# File patterns that exempt tests from specific checks
MAGIC_VALUE_EXEMPT_PATTERNS: Final[frozenset[str]] = frozenset({
    "plural", "unicode", "cache", "diagnostic", "code", "date", "parsing"
})

# File patterns for parser/AST tests (higher assertion threshold)
PARSER_TEST_PATTERNS: Final[frozenset[str]] = frozenset({
    "parser", "ast", "syntax", "parse"
})

# Logging fixture names (exempt from broad exception checks)
LOGGING_FIXTURES: Final[frozenset[str]] = frozenset({
    "caplog", "capsys", "capfd", "logger"
})

# Hardcoded path patterns indicating platform-specific test data
HARDCODED_PATH_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r'["\']\/Users\/[^"\']+["\']'),  # macOS user paths
    re.compile(r'["\']\/home\/[^"\']+["\']'),  # Linux user paths
    re.compile(r'["\'][A-Za-z]:\\[^"\']+["\']'),  # Windows paths
    re.compile(r'["\']\/tmp\/[^"\']+["\']'),  # Hardcoded /tmp (use tmp_path)
)

# Flaky test indicators - functions that introduce non-determinism
FLAKY_RANDOM_FUNCTIONS: Final[frozenset[str]] = frozenset({
    "random", "randint", "randrange", "choice", "choices", "shuffle",
    "sample", "uniform", "gauss", "normalvariate",
})

# Bad test filename patterns
BAD_FILENAME_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"^test_test_"), "Redundant 'test_test_' prefix"),
    (re.compile(r"^test_[0-9]+\.py$"), "Numbered test file without description"),
    (re.compile(r"^test_misc\.py$"), "Generic 'misc' name"),
    (re.compile(r"^test_stuff\.py$"), "Generic 'stuff' name"),
    (re.compile(r"^test_things\.py$"), "Generic 'things' name"),
    (re.compile(r"^test_utils\.py$"), "Generic 'utils' - what is being tested?"),
    (re.compile(r"^test_helpers\.py$"), "Generic 'helpers' - what is being tested?"),
    (re.compile(r"^test_new\.py$"), "Placeholder 'new' name"),
    (re.compile(r"^test_old\.py$"), "Placeholder 'old' name"),
    (re.compile(r"^test_temp\.py$"), "Temporary file name"),
    (re.compile(r"^test_tmp\.py$"), "Temporary file name"),
    (re.compile(r"^test_wip\.py$"), "Work-in-progress file name"),
    (re.compile(r"^test_todo\.py$"), "TODO file name"),
    (re.compile(r"^test_fixme\.py$"), "FIXME file name"),
    (re.compile(r"^tests?\.py$"), "Generic 'test(s).py' without subject"),
    # Coverage/completion anti-patterns - use descriptive module names
    (re.compile(r"_100_percent\.py$"), "Use descriptive module name, not '100 percent'"),
    (re.compile(r"_final\.py$"), "Placeholder 'final' suffix - what is being tested?"),
    (re.compile(r"_targeted\.py$"), "Use descriptive name instead of 'targeted'"),
    (re.compile(r"_complete\.py$"), "Use descriptive name instead of 'complete'"),
    (re.compile(r"_v[0-9]+\.py$"), "Version suffix should be removed after migration"),
)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass(frozen=True, slots=True)
class Config:
    """Analyzer configuration with sensible defaults.

    Can be loaded from pyproject.toml [tool.test-smells] section.
    """

    assertion_threshold: int = ASSERTION_OVERLOAD_THRESHOLD
    assertion_threshold_parser: int = 15  # Higher for parser/AST tests
    mock_threshold: int = MOCK_OVERUSE_THRESHOLD
    min_test_name_length: int = MIN_TEST_NAME_LENGTH
    magic_number_threshold: int = MAGIC_NUMBER_THRESHOLD
    exempt_years: tuple[int, int] = (1900, 2100)  # Year range to exempt
    exempt_magic_patterns: frozenset[str] = MAGIC_VALUE_EXEMPT_PATTERNS
    parser_patterns: frozenset[str] = PARSER_TEST_PATTERNS


def load_config(project_root: Path | None = None) -> Config:
    """Load configuration from pyproject.toml if available."""
    if project_root is None:
        project_root = Path.cwd()

    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return Config()

    try:
        # Parse TOML manually (no tomllib dependency for Python 3.10 compat)
        content = pyproject.read_text(encoding="utf-8")
        if "[tool.test-smells]" not in content:
            return Config()

        # Extract section (simple parsing for common keys)
        # Full TOML parsing would require tomllib (Python 3.11+)
        assertion_threshold: int | None = None
        mock_threshold: int | None = None
        min_test_name_length: int | None = None

        # Look for integer values
        key_map = {
            "assertion-threshold": "assertion_threshold",
            "mock-threshold": "mock_threshold",
            "min-test-name-length": "min_test_name_length",
        }
        for toml_key, var_name in key_map.items():
            pattern = f"{toml_key} = "
            for line in content.splitlines():
                if pattern in line:
                    try:
                        val = int(line.split("=")[1].strip())
                        if var_name == "assertion_threshold":
                            assertion_threshold = val
                        elif var_name == "mock_threshold":
                            mock_threshold = val
                        elif var_name == "min_test_name_length":
                            min_test_name_length = val
                    except (ValueError, IndexError):
                        pass
                    break

        # Build config with parsed values or defaults
        return Config(
            assertion_threshold=assertion_threshold or ASSERTION_OVERLOAD_THRESHOLD,
            mock_threshold=mock_threshold or MOCK_OVERUSE_THRESHOLD,
            min_test_name_length=min_test_name_length or MIN_TEST_NAME_LENGTH,
        )

    except OSError:
        return Config()


# =============================================================================
# DATA STRUCTURES
# =============================================================================


class Severity(StrEnum):
    """Smell severity levels ordered by priority."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


SEVERITY_ORDER: Final[dict[Severity, int]] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


@dataclass(frozen=True, slots=True)
class Smell:
    """Detected test smell with location and severity."""

    category: str
    severity: Severity
    file: Path
    line: int
    description: str
    snippet: str = ""
    rule_id: str = ""  # For SARIF output


@dataclass(slots=True)
class FunctionStats:
    """Statistics collected in a single AST pass for efficiency.

    Instead of walking the AST multiple times for each check, we collect
    all relevant node information in one pass.
    """

    assertions: list[ast.Assert] = field(default_factory=list)
    loops: list[ast.For | ast.While] = field(default_factory=list)
    conditionals: list[ast.If] = field(default_factory=list)
    exception_handlers: list[ast.ExceptHandler] = field(default_factory=list)
    try_blocks: list[ast.Try] = field(default_factory=list)
    calls: list[ast.Call] = field(default_factory=list)
    with_blocks: list[ast.With] = field(default_factory=list)
    constants: list[ast.Constant] = field(default_factory=list)
    names: list[ast.Name] = field(default_factory=list)
    attributes: list[ast.Attribute] = field(default_factory=list)


@dataclass(slots=True)
class SmellReport:
    """Collection of detected smells with statistics."""

    smells: list[Smell] = field(default_factory=list)
    files_analyzed: int = 0
    tests_analyzed: int = 0

    SEVERITY_ORDER: ClassVar[dict[Severity, int]] = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }

    def add(self, smell: Smell) -> None:
        """Add smell to report."""
        self.smells.append(smell)

    def sort_by_severity(self) -> None:
        """Sort smells by severity, then file, then line."""
        self.smells.sort(key=lambda s: (self.SEVERITY_ORDER[s.severity], str(s.file), s.line))

    def count_by_severity(self, severity: Severity) -> int:
        """Count smells of a specific severity."""
        return sum(1 for s in self.smells if s.severity == severity)

    def to_dict(self) -> dict[str, object]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "summary": {
                "files_analyzed": self.files_analyzed,
                "tests_analyzed": self.tests_analyzed,
                "total_smells": len(self.smells),
                "critical": self.count_by_severity(Severity.CRITICAL),
                "high": self.count_by_severity(Severity.HIGH),
                "medium": self.count_by_severity(Severity.MEDIUM),
                "low": self.count_by_severity(Severity.LOW),
            },
            "smells": [
                {
                    "category": s.category,
                    "severity": s.severity.value,
                    "file": str(s.file),
                    "line": s.line,
                    "description": s.description,
                    "snippet": s.snippet,
                }
                for s in self.smells
            ],
        }

    def to_sarif(self) -> dict[str, object]:
        """Convert report to SARIF format for IDE integration.

        SARIF (Static Analysis Results Interchange Format) is a standard
        JSON-based format for representing static analysis results.
        """
        # Map severity to SARIF levels
        severity_to_level: dict[Severity, str] = {
            Severity.CRITICAL: "error",
            Severity.HIGH: "warning",
            Severity.MEDIUM: "note",
            Severity.LOW: "note",
        }

        # Collect unique rules
        rules: dict[str, dict[str, object]] = {}
        results: list[dict[str, object]] = []

        for smell in self.smells:
            rule_id = smell.rule_id or smell.category.lower().replace(" ", "-")

            if rule_id not in rules:
                rules[rule_id] = {
                    "id": rule_id,
                    "name": smell.category,
                    "shortDescription": {"text": smell.category},
                    "defaultConfiguration": {
                        "level": severity_to_level[smell.severity]
                    },
                }

            results.append({
                "ruleId": rule_id,
                "level": severity_to_level[smell.severity],
                "message": {"text": smell.description},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": str(smell.file)},
                        "region": {"startLine": smell.line},
                    }
                }],
            })

        return {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "test-smell-analyzer",
                        "version": "1.0.0",
                        "informationUri": "https://github.com/example/test-smell-analyzer",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }],
        }

    def group_by_file(self) -> dict[Path, list[Smell]]:
        """Group smells by file path for --by-file output mode."""
        by_file: dict[Path, list[Smell]] = {}
        for smell in self.smells:
            by_file.setdefault(smell.file, []).append(smell)
        # Sort smells within each file by severity then line
        for smells in by_file.values():
            smells.sort(key=lambda s: (self.SEVERITY_ORDER[s.severity], s.line))
        return by_file

    def filter_by_severity(self, filter_spec: str) -> None:
        """Filter smells to only include specified severities.

        Args:
            filter_spec: Comma-separated severities or severity+ for that level and above
                         e.g., "critical,high" or "medium+"
        """
        if filter_spec.endswith("+"):
            # "medium+" means medium and above (medium, high, critical)
            base = filter_spec[:-1].upper()
            base_order = self.SEVERITY_ORDER.get(Severity(base), 3)
            allowed = {s for s, order in self.SEVERITY_ORDER.items() if order <= base_order}
        else:
            # Comma-separated list
            allowed = {Severity(s.strip().upper()) for s in filter_spec.split(",")}

        self.smells = [s for s in self.smells if s.severity in allowed]


def parse_waiver_comment(line: str) -> set[str]:
    """Extract waiver codes from inline comments.

    Recognizes:
    - # noqa: XXX, YYY
    - # pylint: disable=xxx, yyy
    - # type: ignore[xxx]
    - # test-smell: ignore[xxx]

    Returns:
        Set of waiver codes found (e.g., {"noqa", "broad-exception-caught"})
    """
    waivers: set[str] = set()

    if "# noqa" in line:
        waivers.add("noqa")
        # Extract specific codes (e.g., E501, W503)
        if "noqa:" in line:
            match = re.search(r"noqa:\s*([A-Z0-9,\s]+)", line, re.IGNORECASE)
            if match:
                for code in match.group(1).split(","):
                    waivers.add(code.strip().lower())

    if "# pylint: disable" in line or "#pylint:disable" in line:
        waivers.add("pylint-disable")
        # Extract specific codes: # pylint: disable=broad-exception-caught
        match = re.search(r"pylint:\s*disable[=\s]+([a-z0-9-,\s]+)", line, re.IGNORECASE)
        if match:
            for code in match.group(1).split(","):
                waivers.add(code.strip().lower())

    if "# type: ignore" in line:
        waivers.add("type-ignore")

    if "# test-smell: ignore" in line:
        waivers.add("test-smell-ignore")
        match = re.search(r"test-smell:\s*ignore\[([^\]]+)\]", line)
        if match:
            for code in match.group(1).split(","):
                waivers.add(code.strip().lower())

    return waivers


# =============================================================================
# AST UTILITIES
# =============================================================================


def walk_without_nested_definitions(node: ast.AST) -> Iterator[ast.AST]:
    """Walk AST nodes but skip nested class and function definitions.

    This prevents false positives when analyzing test functions that define
    helper classes or nested functions.
    """
    for child in ast.iter_child_nodes(node):
        yield child
        # Don't descend into nested class or function definitions
        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yield from walk_without_nested_definitions(child)


def is_hypothesis_decorated(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if function has Hypothesis decorators."""
    for decorator in node.decorator_list:
        match decorator:
            # @given, @settings, @example
            case ast.Name(id=name) if name in HYPOTHESIS_DECORATORS:
                return True
            # @given(...), @settings(...), @example(...)
            case ast.Call(func=ast.Name(id=name)) if name in HYPOTHESIS_DECORATORS:
                return True
            # @hypothesis.given, @hypothesis.settings
            case ast.Attribute(attr=attr) if attr in HYPOTHESIS_DECORATORS:
                return True
            # @hypothesis.given(...), @hypothesis.settings(...)
            case ast.Call(func=ast.Attribute(attr=attr)) if attr in HYPOTHESIS_DECORATORS:
                return True
    return False


def is_skipped_test(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if test has skip decorator (pytest.mark.skip or unittest.skip)."""
    skip_names = {"skip", "skipIf", "skipUnless", "xfail"}
    for decorator in node.decorator_list:
        match decorator:
            # @skip, @xfail
            case ast.Name(id=name) if name in skip_names:
                return True
            # @skip(...), @xfail(...)
            case ast.Call(func=ast.Name(id=name)) if name in skip_names:
                return True
            # @pytest.mark.skip, @unittest.skip
            case ast.Attribute(attr=attr) if attr in skip_names:
                return True
            # @pytest.mark.skip(...), @unittest.skip(...)
            case ast.Call(func=ast.Attribute(attr=attr)) if attr in skip_names:
                return True
    return False


def count_assertions(node: ast.AST) -> int:
    """Count assert statements in an AST node."""
    return sum(1 for _ in ast.walk(node) if isinstance(_, ast.Assert))


def has_pytest_raises(node: ast.AST) -> bool:
    """Check if node contains pytest.raises context manager."""
    for child in ast.walk(node):
        if not isinstance(child, ast.With):
            continue
        for item in child.items:
            match item.context_expr:
                case ast.Call(func=ast.Attribute(attr="raises")):
                    # Matches pytest.raises(ExceptionType)
                    return True
                case ast.Call(func=ast.Name(id="raises")):
                    # Matches directly imported raises(ExceptionType)
                    return True
    return False


def has_caplog_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if test function uses caplog fixture (logging tests)."""
    return any(arg.arg == "caplog" for arg in node.args.args)


def is_concurrency_test(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if test is a concurrency/thread-safety test."""
    concurrency_keywords = {"concurrent", "thread", "parallel", "race", "deadlock"}
    name_lower = node.name.lower()
    return any(kw in name_lower for kw in concurrency_keywords)


def is_coverage_or_error_test(
    node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: Path
) -> bool:
    """Check if test is a coverage/error path test that may swallow exceptions."""
    # Keywords in test name that suggest legitimate exception swallowing
    name_keywords = {
        "coverage", "error", "exception", "gaps", "edge", "platform", "compat", "protocol"
    }
    # Keywords in file name that suggest comprehensive/coverage tests
    file_keywords = {"coverage", "comprehensive", "gaps", "edge"}

    name_lower = node.name.lower()
    file_lower = file_path.name.lower()

    # Check test name or file name for coverage keywords
    return any(kw in name_lower for kw in name_keywords) or any(
        kw in file_lower for kw in file_keywords
    )


def is_type_guard_conditional(node: ast.If) -> bool:  # noqa: PLR0911
    """Check if conditional is a type guard or result inspection (required for type narrowing)."""
    match node.test:
        # if x is not None:
        case ast.Compare(ops=[ast.IsNot()], comparators=[ast.Constant(value=None)]):
            return True
        # if x is None:
        case ast.Compare(ops=[ast.Is()], comparators=[ast.Constant(value=None)]):
            return True
        # if isinstance(x, Type):
        case ast.Call(func=ast.Name(id="isinstance")):
            return True
        # if hasattr(x, "attr"):
        case ast.Call(func=ast.Name(id="hasattr")):
            return True
        # if x.attr is not None: (attribute check)
        case ast.Compare(
            left=ast.Attribute(),
            ops=[ast.IsNot() | ast.Is()],
            comparators=[ast.Constant(value=None)],
        ):
            return True
        # if len(x) > 0: or if len(x) == 0: (result length check)
        case ast.Compare(left=ast.Call(func=ast.Name(id="len"))):
            return True
        # if callable(x):
        case ast.Call(func=ast.Name(id="callable")):
            return True
        # if getattr(x, "attr", None):
        case ast.Call(func=ast.Name(id="getattr")):
            return True
    return False


def is_search_loop(loop_node: ast.For) -> bool:
    """Check if loop is searching within results (not iterating test cases).

    Search patterns:
    - Loop with break/return inside
    - Loop variable only used for condition checking
    - Result assigned and used after loop
    """
    # Check for break or return inside loop
    for child in ast.walk(loop_node):
        if isinstance(child, (ast.Break, ast.Return)):
            return True

    # Check if loop body is mostly conditionals (searching for a match)
    conditional_count = sum(1 for stmt in loop_node.body if isinstance(stmt, ast.If))
    return conditional_count > 0 and len(loop_node.body) <= 2


def is_cleanup_loop(loop_node: ast.For | ast.While, func_node: ast.AST) -> bool:
    """Check if loop is cleanup code (e.g., in finally block or teardown).

    Cleanup patterns:
    - Loop in finally block
    - Loop deleting from sys.modules or similar cleanup
    - Loop calling .close(), .cleanup(), etc.
    """
    loop_line = loop_node.lineno

    # Check if loop is inside a finally block
    for node in ast.walk(func_node):
        if isinstance(node, ast.Try) and node.finalbody:
            for stmt in node.finalbody:
                # Check if loop is within the finally block
                if hasattr(stmt, "lineno"):
                    finally_start = stmt.lineno
                    finally_end = max(
                        getattr(s, "lineno", 0) for s in ast.walk(stmt)
                    )
                    if finally_start <= loop_line <= finally_end:
                        return True

    # Check loop body for cleanup patterns
    cleanup_patterns = {"close", "cleanup", "restore", "shutdown", "clear"}
    for child in ast.walk(loop_node):
        if isinstance(child, ast.Delete):
            return True
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in cleanup_patterns
        ):
            return True

    return False


# =============================================================================
# SMELL DETECTOR
# =============================================================================


class TestSmellDetector(ast.NodeVisitor):
    """AST visitor to detect test smells."""

    def __init__(
        self, file_path: Path, source: str, config: Config | None = None
    ) -> None:
        """Initialize detector with file path and source code."""
        self.file_path = file_path
        self.source = source
        self.lines = source.splitlines()
        self.smells: list[Smell] = []
        self.test_count = 0
        self._current_class: str | None = None
        self._in_test_function = False
        self._config = config or Config()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track current class context."""
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Analyze test function for smells."""
        self._analyze_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Analyze async test function for smells."""
        self._analyze_function(node)

    def _analyze_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Run all smell checks on a function definition."""
        if not node.name.startswith("test_"):
            self.generic_visit(node)
            return

        # Skip nested functions inside test functions (helper functions like test_func)
        if self._in_test_function:
            self.generic_visit(node)
            return

        self.test_count += 1
        old_in_test = self._in_test_function
        self._in_test_function = True

        # Run all checks
        self._check_no_assertions(node)
        self._check_empty_body(node)
        self._check_assertion_overload(node)
        self._check_weak_assertions(node)
        self._check_singleton_equality(node)
        self._check_broad_exceptions(node)
        self._check_exception_swallowing(node)
        self._check_try_except_instead_of_raises(node)
        self._check_conditional_logic(node)
        self._check_loops_without_hypothesis(node)
        self._check_magic_values(node)
        self._check_poor_naming(node)
        self._check_io_operations(node)
        self._check_time_operations(node)
        self._check_excessive_mocking(node)
        self._check_print_statements(node)
        # New detections
        self._check_duplicate_assertions(node)
        self._check_flaky_indicators(node)
        self._check_incomplete_cleanup(node)
        self._check_hardcoded_paths(node)

        self.generic_visit(node)
        self._in_test_function = old_in_test

    def _add_smell(
        self,
        category: str,
        severity: Severity,
        line: int,
        description: str,
        snippet: str = "",
        rule_id: str = "",
    ) -> None:
        """Add a smell to the collection."""
        self.smells.append(
            Smell(
                category=category,
                severity=severity,
                file=self.file_path,
                line=line,
                description=description,
                snippet=snippet,
                rule_id=rule_id or category.lower().replace(" ", "-"),
            )
        )

    def _get_line(self, lineno: int) -> str:
        """Get source line by number (1-indexed)."""
        if 0 < lineno <= len(self.lines):
            return self.lines[lineno - 1]
        return ""

    # -------------------------------------------------------------------------
    # SMELL CHECKS
    # -------------------------------------------------------------------------

    def _check_no_assertions(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect tests with no assertions."""
        # Skip tests marked with skip/xfail decorators (intentionally not implemented)
        if is_skipped_test(node):
            return

        has_assert = count_assertions(node) > 0
        has_raises = has_pytest_raises(node)

        if has_assert or has_raises:
            return

        # Skip if it's a placeholder test (pass-only or docstring-only)
        body_without_docstring = node.body
        if (
            body_without_docstring
            and isinstance(body_without_docstring[0], ast.Expr)
            and isinstance(body_without_docstring[0].value, ast.Constant)
            and isinstance(body_without_docstring[0].value.value, str)
        ):
            body_without_docstring = body_without_docstring[1:]

        if len(body_without_docstring) == 1 and isinstance(body_without_docstring[0], ast.Pass):
            return

        self._add_smell(
            category="Tests Without Assertions",
            severity=Severity.CRITICAL,
            line=node.lineno,
            description=f"Test '{node.name}' has no assertions",
        )

    def _check_empty_body(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect tests with empty bodies (only docstring)."""
        # Skip tests marked with skip/xfail decorators (intentionally not implemented)
        if is_skipped_test(node):
            return

        # Check if body is only a docstring
        if len(node.body) == 1:
            match node.body[0]:
                case ast.Expr(value=ast.Constant(value=str())):
                    self._add_smell(
                        category="Empty Test Body",
                        severity=Severity.HIGH,
                        line=node.lineno,
                        description=f"Test '{node.name}' has only a docstring, no implementation",
                    )

    def _check_assertion_overload(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect tests with too many assertions (non-property tests)."""
        if is_hypothesis_decorated(node):
            return

        # Use higher threshold for parser/AST tests (complex structure verification)
        file_lower = self.file_path.name.lower()
        is_parser_test = any(p in file_lower for p in self._config.parser_patterns)
        threshold = (
            self._config.assertion_threshold_parser
            if is_parser_test
            else self._config.assertion_threshold
        )

        assertion_count = count_assertions(node)
        if assertion_count > threshold:
            self._add_smell(
                category="Assertion Overload",
                severity=Severity.MEDIUM,
                line=node.lineno,
                description=(
                    f"Test '{node.name}' has {assertion_count} assertions "
                    f"(>{threshold})"
                ),
            )

    def _check_weak_assertions(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect weak/tautological assertions."""
        for child in ast.walk(node):
            if not isinstance(child, ast.Assert):
                continue

            line_text = self._get_line(child.lineno)

            # Check for assert True without justification
            match child.test:
                case ast.Constant(value=True):
                    # Only allow if comment explicitly justifies it
                    if "#" not in line_text or "defensive" not in line_text.lower():
                        self._add_smell(
                            category="Weak Assertions",
                            severity=Severity.HIGH,
                            line=child.lineno,
                            description="assert True without clear justification",
                            snippet=line_text.strip(),
                        )

            # Check for tautological assertions: assert x is not None or x is None
            match child.test:
                case ast.BoolOp(op=ast.Or(), values=values) if len(values) == 2:
                    if "is not None or" in line_text and "is None" in line_text:
                        self._add_smell(
                            category="Weak Assertions",
                            severity=Severity.HIGH,
                            line=child.lineno,
                            description="Tautological assertion always passes",
                            snippet=line_text.strip(),
                        )

    def _check_singleton_equality(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect assert x == None instead of assert x is None."""
        for child in ast.walk(node):
            if not isinstance(child, ast.Assert):
                continue

            match child.test:
                case ast.Compare(
                    ops=[ast.Eq() | ast.NotEq()],
                    comparators=[ast.Constant(value=None)],
                ):
                    line_text = self._get_line(child.lineno)
                    self._add_smell(
                        category="Singleton Equality",
                        severity=Severity.MEDIUM,
                        line=child.lineno,
                        description="Use 'is None'/'is not None' instead of '=='/'!=' None",
                        snippet=line_text.strip(),
                    )
                case ast.Compare(
                    ops=[ast.Eq() | ast.NotEq()],
                    comparators=[ast.Constant(value=True | False)],
                ):
                    line_text = self._get_line(child.lineno)
                    self._add_smell(
                        category="Singleton Equality",
                        severity=Severity.LOW,
                        line=child.lineno,
                        description="Use 'is True/False' instead of '== True/False'",
                        snippet=line_text.strip(),
                    )

    def _check_broad_exceptions(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect overly broad exception handling."""
        # Skip concurrency tests - thread workers legitimately catch all exceptions
        if is_concurrency_test(node):
            return

        # Skip Hypothesis tests - property tests may catch broad exceptions intentionally
        if is_hypothesis_decorated(node):
            return

        # Skip error/exception tests - they intentionally test exception handling
        name_lower = node.name.lower()
        if "error" in name_lower or "exception" in name_lower:
            return

        # Skip logging tests - exception swallowing is legitimate when testing log output
        if any(arg.arg in LOGGING_FIXTURES for arg in node.args.args):
            return

        for child in ast.walk(node):
            if not isinstance(child, ast.ExceptHandler):
                continue

            match child.type:
                case None:
                    self._add_smell(
                        category="Broad Exception Handling",
                        severity=Severity.HIGH,
                        line=child.lineno,
                        description="Bare except catches all exceptions incl. KeyboardInterrupt",
                    )
                case ast.Name(id="Exception"):
                    self._add_smell(
                        category="Broad Exception Handling",
                        severity=Severity.MEDIUM,
                        line=child.lineno,
                        description="Catching generic Exception instead of specific type",
                    )
                case ast.Name(id="BaseException"):
                    self._add_smell(
                        category="Broad Exception Handling",
                        severity=Severity.HIGH,
                        line=child.lineno,
                        description="Catching BaseException is almost always wrong",
                    )

    def _check_exception_swallowing(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect except blocks that swallow exceptions."""
        # Skip logging tests - exception swallowing is legitimate when testing log output
        if has_caplog_fixture(node):
            return

        # Skip Hypothesis tests - expected exceptions are often swallowed intentionally
        if is_hypothesis_decorated(node):
            return

        # Skip concurrency tests - thread workers legitimately catch all exceptions
        if is_concurrency_test(node):
            return

        # Skip coverage/error path tests - platform edge cases may be swallowed
        if is_coverage_or_error_test(node, self.file_path):
            return

        for child in ast.walk(node):
            if not isinstance(child, ast.ExceptHandler):
                continue

            # Check if body is just 'pass' or '...'
            if len(child.body) == 1:
                match child.body[0]:
                    case ast.Pass():
                        self._add_smell(
                            category="Exception Swallowing",
                            severity=Severity.HIGH,
                            line=child.lineno,
                            description="Exception silently swallowed with 'pass'",
                        )
                    case ast.Expr(value=ast.Constant(value=val)) if val is ...:
                        self._add_smell(
                            category="Exception Swallowing",
                            severity=Severity.HIGH,
                            line=child.lineno,
                            description="Exception silently swallowed with '...'",
                        )

    def _check_try_except_instead_of_raises(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Detect try/except used instead of pytest.raises."""
        for child in ast.walk(node):
            if not isinstance(child, ast.Try):
                continue

            # Look for assert False pattern in try body
            for stmt in child.body:
                match stmt:
                    case ast.Assert(test=ast.Constant(value=False)):
                        self._add_smell(
                            category="Missing pytest.raises",
                            severity=Severity.MEDIUM,
                            line=child.lineno,
                            description="Use pytest.raises instead of try/except/assert False",
                        )
                        break

            # Look for "expected exception" fail pattern
            if child.handlers:
                for stmt in child.body:
                    match stmt:
                        case ast.Raise():
                            # Re-raising after logging is OK
                            continue
                        case ast.Expr(value=ast.Call(func=ast.Attribute(attr="fail"))):
                            self._add_smell(
                                category="Missing pytest.raises",
                                severity=Severity.MEDIUM,
                                line=child.lineno,
                                description="Use pytest.raises instead of try/except/pytest.fail",
                            )
                            break

    def _check_conditional_logic(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect conditional logic in tests (anti-pattern)."""
        # Skip hypothesis property tests - conditionals are often legitimate
        if is_hypothesis_decorated(node):
            return

        # Skip coverage/error path tests - conditionals expected for error inspection
        if is_coverage_or_error_test(node, self.file_path):
            return

        # Use custom walker to skip nested class/function definitions
        for child in walk_without_nested_definitions(node):
            if not isinstance(child, ast.If):
                continue

            # Exception: Type guards required for type narrowing (mypy strict)
            if is_type_guard_conditional(child):
                continue

            # Exception: Result-guard conditionals (if errors: / if result:)
            if self._is_result_guard_conditional(child):
                continue

            line_text = self._get_line(child.lineno)

            # Exception: Hypothesis assume() is OK
            if "assume(" in line_text:
                continue

            # Exception: TYPE_CHECKING guards are OK
            if "TYPE_CHECKING" in line_text:
                continue

            # Exception: Platform checks are OK
            if "sys.platform" in line_text or "platform." in line_text:
                continue

            # Exception: Environment checks are OK
            if "os.environ" in line_text or "importlib" in line_text:
                continue

            self._add_smell(
                category="Conditional Logic in Tests",
                severity=Severity.MEDIUM,
                line=child.lineno,
                description="Conditional logic makes test behavior unclear; use parametrize",
            )

    def _is_result_guard_conditional(self, if_node: ast.If) -> bool:  # noqa: PLR0911
        """Check if conditional guards optional result inspection."""
        # if errors: / if result: / if log_messages: / if warnings:
        result_guard_names = {"errors", "result", "log_messages", "warnings", "messages"}
        match if_node.test:
            case ast.Name(id=name) if name in result_guard_names:
                return True
            # if not errors: / if not result:
            case ast.UnaryOp(op=ast.Not(), operand=ast.Name(id=name)) if name in result_guard_names:
                return True
            # if x == "value": (checking result/property equality)
            case ast.Compare(ops=[ast.Eq() | ast.NotEq()]):
                return True
            # if x.startswith("_"): (method call checks on iteration variables)
            case ast.Call(func=ast.Attribute(attr="startswith" | "endswith")):
                return True
            # if result.is_valid: / if not result.is_valid: (validation outcomes)
            case ast.Attribute(attr="is_valid"):
                return True
            case ast.UnaryOp(op=ast.Not(), operand=ast.Attribute(attr="is_valid")):
                return True
            # if count >= N: (performance threshold checks)
            case ast.Compare(ops=[ast.GtE() | ast.LtE() | ast.Gt() | ast.Lt()]):
                # Check if comparing a count-like variable to a number threshold
                if self._is_threshold_check(if_node.test):
                    return True
        return False

    def _is_threshold_check(self, test: ast.Compare) -> bool:
        """Check if comparison is a threshold check (e.g., count >= 50)."""
        threshold_names = {"count", "size", "length", "num", "n", "message_count"}
        match test:
            case ast.Compare(left=ast.Name(id=name), comparators=[ast.Constant(value=val)]):
                if any(kw in name.lower() for kw in threshold_names) and isinstance(val, int):
                    return True
        return False

    def _check_loops_without_hypothesis(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Detect loops in non-property-based tests."""
        if is_hypothesis_decorated(node):
            return

        # Skip performance/stress/benchmark tests
        name_lower = node.name.lower()
        if any(kw in name_lower for kw in ("performance", "stress", "benchmark", "perf")):
            return

        # Use custom walker to skip nested function definitions
        for child in walk_without_nested_definitions(node):
            match child:
                case ast.For() | ast.While():
                    line_text = self._get_line(child.lineno)
                    # Exception: iterating over pytest.mark.parametrize-like fixtures
                    if "parametrize" in line_text.lower():
                        continue
                    # Exception: structural loops for concurrency (threads, processes, etc.)
                    if self._is_structural_loop(child):
                        continue
                    # Exception: result validation loops (checking properties of all elements)
                    if self._is_validation_loop(child):
                        continue
                    # Exception: setup loops (before any assertions)
                    if self._is_setup_loop(child, node):
                        continue
                    # Exception: search loops (searching within results, not iterating cases)
                    if isinstance(child, ast.For) and is_search_loop(child):
                        continue
                    # Exception: cleanup loops (in finally blocks or doing teardown)
                    if is_cleanup_loop(child, node):
                        continue
                    self._add_smell(
                        category="Loops in Tests",
                        severity=Severity.MEDIUM,
                        line=child.lineno,
                        description="Loop in test suggests multiple cases; use parametrize",
                    )

    def _is_structural_loop(self, loop_node: ast.For | ast.While) -> bool:
        """Check if loop is structural (thread/process management, not test cases)."""
        # Structural variable names
        structural_names = {"thread", "process", "future", "task", "worker", "job"}

        if isinstance(loop_node, ast.For):
            # Check loop variable name: for thread in threads
            target = loop_node.target
            if isinstance(target, ast.Name) and target.id.lower() in structural_names:
                return True

            # Check iterable name: for t in threads
            match loop_node.iter:
                case ast.Name(id=name):
                    name_lower = name.lower()
                    if any(s in name_lower for s in structural_names):
                        return True

            # Check for range-based structural loops: for _ in range(num_threads)
            match loop_node.iter:
                case ast.Call(func=ast.Name(id="range")):
                    # Check if any arg contains structural name
                    for arg in loop_node.iter.args:
                        if isinstance(arg, ast.Name) and any(
                            s in arg.id.lower() for s in structural_names
                        ):
                            return True

        # Check loop body for structural method calls (.start(), .join(), .result())
        structural_methods = {"start", "join", "result", "wait", "shutdown"}
        for stmt in ast.walk(loop_node):
            match stmt:
                case ast.Call(func=ast.Attribute(attr=attr)) if attr in structural_methods:
                    return True

        return False

    def _is_validation_loop(self, loop_node: ast.For | ast.While) -> bool:
        """Check if loop is validating properties of result elements."""
        if not isinstance(loop_node, ast.For):
            return False

        # Check if loop body contains only assertions
        non_assertion_stmts = [
            stmt for stmt in loop_node.body
            if not isinstance(stmt, ast.Assert)
            and not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        ]

        # If loop body is mostly/only assertions, it's a validation loop
        if len(non_assertion_stmts) <= 1 and any(isinstance(s, ast.Assert) for s in loop_node.body):
            return True

        # Check for common validation patterns: for item in collection: assert ...
        match loop_node.iter:
            case ast.Call(func=ast.Attribute(attr="values" | "items" | "keys")):
                # Iterating over dict methods
                return True
            case ast.Name():
                # Check if iterating over something named "results", "values", "items", etc.
                iter_name = loop_node.iter.id if isinstance(loop_node.iter, ast.Name) else ""
                validation_names = {"results", "values", "items", "elements", "entries"}
                if any(vn in iter_name.lower() for vn in validation_names):
                    return True

        return False

    def _is_setup_loop(
        self, loop_node: ast.For | ast.While, func_node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> bool:
        """Check if loop appears before any assertions (setup phase)."""
        loop_lineno = loop_node.lineno

        # Check if any assertions appear before this loop
        for child in ast.walk(func_node):
            if isinstance(child, ast.Assert) and child.lineno < loop_lineno:
                return False  # There are assertions before this loop

        # No assertions before this loop - likely setup
        return True

    def _check_magic_values(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect unexplained magic values in assertions."""
        # Skip if file/test name suggests valid numeric testing
        file_lower = self.file_path.name.lower()
        name_lower = node.name.lower()
        if any(p in file_lower for p in self._config.exempt_magic_patterns):
            return
        if any(p in name_lower for p in self._config.exempt_magic_patterns):
            return

        year_min, year_max = self._config.exempt_years

        for child in ast.walk(node):
            if not isinstance(child, ast.Assert):
                continue

            line_text = self._get_line(child.lineno)

            threshold = self._config.magic_number_threshold
            for subnode in ast.walk(child.test):
                match subnode:
                    case ast.Constant(value=int() as val) if abs(val) > threshold:
                        # Skip if there's an explanatory comment
                        if "#" in line_text:
                            continue
                        # Skip common round values that are self-explanatory
                        if val in {1000, 10000, 100000, 1000000}:
                            continue
                        # Skip year-like values (dates are self-documenting)
                        if year_min <= val <= year_max:
                            continue
                        # Skip hex literals (Unicode code points, etc.)
                        if "0x" in line_text or "0X" in line_text:
                            continue
                        self._add_smell(
                            category="Magic Values",
                            severity=Severity.LOW,
                            line=child.lineno,
                            description=f"Large magic number {val} without explanation",
                            snippet=line_text.strip(),
                        )

    def _check_poor_naming(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect poorly named tests."""
        name = node.name
        name_lower = name.lower()

        # Check for very short names
        if len(name) < MIN_TEST_NAME_LENGTH:
            self._add_smell(
                category="Poor Test Naming",
                severity=Severity.LOW,
                line=node.lineno,
                description=f"Test name '{name}' is too short to be descriptive",
            )
            return  # Don't double-report

        # Check for exact match generic names
        if name_lower in GENERIC_TEST_EXACT:
            self._add_smell(
                category="Poor Test Naming",
                severity=Severity.MEDIUM,
                line=node.lineno,
                description=f"Test name '{name}' is too generic",
            )
            return

        # Check for generic prefixes
        for prefix in GENERIC_TEST_PREFIXES:
            if name_lower.startswith(prefix):
                self._add_smell(
                    category="Poor Test Naming",
                    severity=Severity.MEDIUM,
                    line=node.lineno,
                    description=f"Test name '{name}' uses generic prefix",
                )
                break

    def _check_io_operations(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect file I/O operations in unit tests."""
        # Skip tests explicitly named for I/O
        name_lower = node.name.lower()
        if any(kw in name_lower for kw in ("file", "io", "read", "write", "path")):
            return

        for child in ast.walk(node):
            match child:
                case ast.Call(func=ast.Name(id="open")):
                    self._add_smell(
                        category="I/O in Unit Tests",
                        severity=Severity.MEDIUM,
                        line=child.lineno,
                        description="File I/O in test; use tmp_path fixture or mock",
                    )

    def _check_time_operations(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect time-dependent operations.

        Exemptions:
            - Tests that explicitly test date/time formatting functionality
            - Performance/benchmark tests (timing is the point)
        """
        # Skip tests that explicitly test date/time or formatting functionality
        name_lower = node.name.lower()
        file_lower = self.file_path.name.lower()
        exempt_keywords = ("date", "time", "format", "locale", "performance", "benchmark")
        if any(kw in name_lower for kw in exempt_keywords):
            return
        if any(kw in file_lower for kw in exempt_keywords):
            return

        for child in ast.walk(node):
            match child:
                case ast.Call(func=ast.Attribute(attr="sleep")):
                    self._add_smell(
                        category="Sleep-Based Synchronization",
                        severity=Severity.HIGH,
                        line=child.lineno,
                        description="time.sleep() makes tests slow and flaky",
                    )
                case ast.Call(func=ast.Attribute(attr="now" | "today" | "utcnow")):
                    self._add_smell(
                        category="Time-Dependent Tests",
                        severity=Severity.MEDIUM,
                        line=child.lineno,
                        description="Time-dependent call should use freezegun or be mocked",
                    )

    def _check_excessive_mocking(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect excessive use of mocks."""
        mock_count = 0
        for child in ast.walk(node):
            match child:
                case ast.Call(func=ast.Name(id="Mock" | "MagicMock" | "patch" | "create_autospec")):
                    mock_count += 1
                case ast.Call(func=ast.Attribute(attr="patch" | "patch_object")):
                    mock_count += 1

        if mock_count > MOCK_OVERUSE_THRESHOLD:
            self._add_smell(
                category="Overuse of Mocks",
                severity=Severity.MEDIUM,
                line=node.lineno,
                description=f"Test uses {mock_count} mocks (>{MOCK_OVERUSE_THRESHOLD})",
            )

    def _check_print_statements(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Detect print statements in tests."""
        for child in ast.walk(node):
            match child:
                case ast.Call(func=ast.Name(id="print")):
                    line_text = self._get_line(child.lineno)
                    # Skip if explicitly for debugging
                    if "# debug" in line_text.lower() or "# TODO" in line_text:
                        continue
                    self._add_smell(
                        category="Print in Tests",
                        severity=Severity.LOW,
                        line=child.lineno,
                        description="print() in test; use logging or capsys fixture",
                    )

    def _check_duplicate_assertions(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Detect exact duplicate assertions (copy-paste errors).

        Exemptions:
            - Type guard assertions (isinstance, is not None) required for mypy strict
            - Empty collection checks (not errors, errors == ())
        """
        assertion_texts: dict[str, list[int]] = {}

        # Patterns that are commonly repeated for type safety (not copy-paste errors)
        type_guard_patterns = {
            "is not None",
            "is None",
            "isinstance(",
            "not errors",
            "errors == ()",
            "errors == []",
        }

        for child in ast.walk(node):
            if not isinstance(child, ast.Assert):
                continue

            # Get the assertion text (normalized)
            try:
                assertion_text = ast.unparse(child.test)
            except (AttributeError, ValueError):
                continue

            # Skip type guard assertions - these are required for mypy strict
            if any(pattern in assertion_text for pattern in type_guard_patterns):
                continue

            assertion_texts.setdefault(assertion_text, []).append(child.lineno)

        # Report duplicates (only if 3+ occurrences to reduce noise)
        for text, lines in assertion_texts.items():
            if len(lines) >= 3:
                # Only first 50 chars for snippet
                snippet = text[:50] + "..." if len(text) > 50 else text
                self._add_smell(
                    category="Duplicate Assertions",
                    severity=Severity.MEDIUM,
                    line=lines[0],
                    description=(
                        f"Same assertion appears {len(lines)} times "
                        f"(lines {', '.join(map(str, lines))})"
                    ),
                    snippet=snippet,
                    rule_id="duplicate-assertion",
                )

    def _check_flaky_indicators(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Detect indicators of flaky tests (random without seed, uuid in assertions)."""
        # Skip Hypothesis tests - randomness is expected and managed
        if is_hypothesis_decorated(node):
            return

        has_random_seed = False
        random_calls: list[tuple[int, str]] = []
        uuid_in_assertions: list[int] = []

        for child in ast.walk(node):
            match child:
                # Check for random.seed() call
                case ast.Call(func=ast.Attribute(attr="seed")):
                    has_random_seed = True
                # Check for random module function calls
                case ast.Call(func=ast.Attribute(value=ast.Name(id="random"), attr=attr)):
                    if attr in FLAKY_RANDOM_FUNCTIONS:
                        random_calls.append((child.lineno, attr))
                # Check for direct random function imports
                case ast.Call(func=ast.Name(id=name)) if name in FLAKY_RANDOM_FUNCTIONS:
                    random_calls.append((child.lineno, name))
                # Check for uuid4() in assertions
                case ast.Assert():
                    for subnode in ast.walk(child):
                        match subnode:
                            case ast.Call(func=ast.Attribute(attr="uuid4")):
                                uuid_in_assertions.append(child.lineno)
                            case ast.Call(func=ast.Name(id="uuid4")):
                                uuid_in_assertions.append(child.lineno)

        # Report random calls without seed
        if random_calls and not has_random_seed:
            line, func = random_calls[0]
            self._add_smell(
                category="Flaky Test Indicator",
                severity=Severity.HIGH,
                line=line,
                description=(
                    f"random.{func}() called without random.seed(); "
                    "test may be non-deterministic"
                ),
                rule_id="flaky-random",
            )

        # Report uuid in assertions
        for line in uuid_in_assertions:
            self._add_smell(
                category="Flaky Test Indicator",
                severity=Severity.MEDIUM,
                line=line,
                description="uuid4() in assertion; generates new value each run",
                rule_id="flaky-uuid",
            )

    def _check_incomplete_cleanup(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Detect incomplete resource cleanup (tempfile without context, chdir without restore)."""
        chdir_calls: list[int] = []

        # Check for fixtures that handle cleanup automatically
        fixture_names = {arg.arg for arg in node.args.args}
        has_cleanup_fixture = bool(fixture_names & {"monkeypatch", "tmp_path"})

        for child in ast.walk(node):
            match child:
                # tempfile without context manager
                case ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="tempfile"),
                        attr="NamedTemporaryFile" | "TemporaryFile" | "TemporaryDirectory"
                    )
                ):
                    if not self._is_inside_with(node, child):
                        self._add_smell(
                            category="Incomplete Cleanup",
                            severity=Severity.MEDIUM,
                            line=child.lineno,
                            description="tempfile created without context manager; may leak",
                            rule_id="incomplete-cleanup-tempfile",
                        )
                # os.chdir or direct chdir detection
                case ast.Call(func=ast.Attribute(value=ast.Name(id="os"), attr="chdir")):
                    chdir_calls.append(child.lineno)
                case ast.Call(func=ast.Name(id="chdir")):
                    chdir_calls.append(child.lineno)

        # Report chdir without restore (single call and no cleanup fixture)
        if len(chdir_calls) == 1 and not has_cleanup_fixture:
            self._add_smell(
                category="Incomplete Cleanup",
                severity=Severity.HIGH,
                line=chdir_calls[0],
                description="os.chdir() without restoring original directory",
                rule_id="incomplete-cleanup-chdir",
            )

    def _is_inside_with(
        self, func_node: ast.FunctionDef | ast.AsyncFunctionDef, target: ast.AST
    ) -> bool:
        """Check if target node is inside a with statement."""
        target_line = getattr(target, "lineno", 0)

        for child in ast.walk(func_node):
            if not isinstance(child, ast.With):
                continue
            # Check if target line is within the with block
            with_start = child.lineno
            with_end = max(
                getattr(stmt, "lineno", 0)
                for stmt in ast.walk(child)
            )
            if with_start <= target_line <= with_end:
                return True
        return False

    def _check_hardcoded_paths(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Detect hardcoded platform-specific paths in tests.

        Exemptions:
            - Tests explicitly testing path/file handling
            - Serializer/escape tests (paths as test data for escape handling)
            - Strings containing FTL placeable syntax { ... }
        """
        # Skip tests that explicitly test path handling or serialization
        name_lower = node.name.lower()
        file_lower = self.file_path.name.lower()
        exempt_keywords = (
            "path", "file", "directory", "platform", "escape",
            "serialize", "literal", "string",
        )
        if any(kw in name_lower for kw in exempt_keywords):
            return
        if any(kw in file_lower for kw in ("serializer", "escape")):
            return

        for child in ast.walk(node):
            match child:
                case ast.Constant(value=str() as val):
                    # Skip if it looks like FTL test data (contains { or })
                    if "{" in val or "}" in val:
                        continue
                    # Skip if it's a test data constructor argument (StringLiteral, etc.)
                    if "\\\\Users\\\\" in val:  # Escaped backslashes for test data
                        continue

                    for pattern in HARDCODED_PATH_PATTERNS:
                        # Check the raw string value
                        if pattern.search(f'"{val}"') or pattern.search(f"'{val}'"):
                            self._add_smell(
                                category="Hardcoded Path",
                                severity=Severity.MEDIUM,
                                line=child.lineno,
                                description=(
                                    "Hardcoded platform-specific path; "
                                    "use tmp_path fixture or relative paths"
                                ),
                                snippet=val[:50] + "..." if len(val) > 50 else val,
                                rule_id="hardcoded-path",
                            )
                            break


def check_bad_filename(file_path: Path) -> Smell | None:
    """Check if test filename follows bad naming patterns."""
    filename = file_path.name

    for pattern, reason in BAD_FILENAME_PATTERNS:
        if pattern.search(filename):
            return Smell(
                category="Bad Test Filename",
                severity=Severity.LOW,
                file=file_path,
                line=1,
                description=f"Test filename issue: {reason}",
                snippet=filename,
                rule_id="bad-filename",
            )

    return None


# =============================================================================
# FILE AND DIRECTORY ANALYSIS
# =============================================================================


def analyze_file(
    file_path: Path,
    config: Config | None = None,
    *,
    check_filename: bool = True,
    respect_waivers: bool = False,
) -> tuple[list[Smell], int]:
    """Analyze single test file for smells.

    Args:
        file_path: Path to the test file.
        config: Optional configuration. Uses defaults if not provided.
        check_filename: Whether to check for bad filename patterns.
        respect_waivers: Skip issues that have inline suppressions.

    Returns:
        Tuple of (smells, test_count)
    """
    smells: list[Smell] = []

    # Check filename first
    if check_filename:
        filename_smell = check_bad_filename(file_path)
        if filename_smell:
            smells.append(filename_smell)

    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[WARN] Cannot read {file_path}: {e}", file=sys.stderr)
        return smells, 0

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        print(f"[WARN] Syntax error in {file_path}: {e}", file=sys.stderr)
        return smells, 0

    detector = TestSmellDetector(file_path, source, config)
    detector.visit(tree)

    # Filter out waived smells if requested
    if respect_waivers:
        source_lines = source.splitlines()
        filtered_smells: list[Smell] = []
        for smell in detector.smells:
            if smell.line <= len(source_lines):
                line_text = source_lines[smell.line - 1]
                waivers = parse_waiver_comment(line_text)
                if not waivers:
                    filtered_smells.append(smell)
            else:
                filtered_smells.append(smell)
        smells.extend(filtered_smells)
    else:
        smells.extend(detector.smells)

    return smells, detector.test_count


def discover_test_files(test_dir: Path) -> Iterator[Path]:
    """Recursively discover test files in directory."""
    # Direct test files
    yield from test_dir.glob("test_*.py")
    yield from test_dir.glob("*_test.py")

    # conftest files
    conftest = test_dir / "conftest.py"
    if conftest.exists():
        yield conftest

    # Recursive discovery in subdirectories
    for subdir in test_dir.iterdir():
        if subdir.is_dir() and not subdir.name.startswith((".", "__")):
            yield from discover_test_files(subdir)


def analyze_directory(
    test_dir: Path,
    config: Config | None = None,
    *,
    exclude_patterns: list[str] | None = None,
    respect_waivers: bool = False,
) -> SmellReport:
    """Analyze all test files in directory recursively.

    Args:
        test_dir: Directory containing test files.
        config: Optional configuration. Attempts to load from pyproject.toml if not provided.
        exclude_patterns: File patterns to exclude from analysis.
        respect_waivers: Skip issues that have inline suppressions.

    Returns:
        SmellReport with all detected smells.
    """
    # Load config from project root if not provided
    if config is None:
        # Walk up to find project root (contains pyproject.toml)
        project_root = test_dir.parent if test_dir.name == "tests" else test_dir
        config = load_config(project_root)

    report = SmellReport()
    exclude_patterns = exclude_patterns or []

    test_files = sorted(set(discover_test_files(test_dir)))

    for test_file in test_files:
        # Check exclusion patterns
        if exclude_patterns:
            file_str = str(test_file)
            if any(pattern in file_str for pattern in exclude_patterns):
                continue

        report.files_analyzed += 1
        smells, test_count = analyze_file(
            test_file, config, respect_waivers=respect_waivers
        )
        report.tests_analyzed += test_count
        for smell in smells:
            report.add(smell)

    report.sort_by_severity()
    return report


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================


def print_report(report: SmellReport, *, verbose: bool = False) -> None:
    """Print smell report to stdout."""
    print("=" * 80)
    print("TEST SMELL ANALYSIS REPORT")
    print("=" * 80)
    print(f"Files analyzed: {report.files_analyzed}")
    print(f"Tests analyzed: {report.tests_analyzed}")
    print(f"Total smells detected: {len(report.smells)}")
    print(f"  CRITICAL: {report.count_by_severity(Severity.CRITICAL)}")
    print(f"  HIGH: {report.count_by_severity(Severity.HIGH)}")
    print(f"  MEDIUM: {report.count_by_severity(Severity.MEDIUM)}")
    print(f"  LOW: {report.count_by_severity(Severity.LOW)}")
    print("=" * 80)

    if not report.smells:
        print("\n[OK] No test smells detected!")
        return

    # Group by category
    by_category: dict[str, list[Smell]] = {}
    for smell in report.smells:
        by_category.setdefault(smell.category, []).append(smell)

    for category in sorted(by_category.keys()):
        smells = by_category[category]
        print(f"\n{category} ({len(smells)} occurrences)")
        print("-" * 80)

        display_limit = None if verbose else 10
        for smell in smells[:display_limit]:
            print(f"  [{smell.severity.value}] {smell.file.name}:{smell.line}")
            print(f"    {smell.description}")
            if smell.snippet and verbose:
                print(f"    > {smell.snippet}")

        if not verbose and len(smells) > 10:
            print(f"  ... and {len(smells) - 10} more (use --verbose to see all)")


def print_json_report(report: SmellReport) -> None:
    """Print smell report as JSON."""
    print(json.dumps(report.to_dict(), indent=2))


def print_sarif_report(report: SmellReport) -> None:
    """Print smell report in SARIF format for IDE integration."""
    print(json.dumps(report.to_sarif(), indent=2))


def print_by_file_report(report: SmellReport, *, verbose: bool = False) -> None:
    """Print smell report grouped by file (for fixing workflow)."""
    print("=" * 80)
    print("TEST SMELL ANALYSIS REPORT (BY FILE)")
    print("=" * 80)
    print(f"Files analyzed: {report.files_analyzed}")
    print(f"Tests analyzed: {report.tests_analyzed}")
    print(f"Total smells detected: {len(report.smells)}")
    print(f"  CRITICAL: {report.count_by_severity(Severity.CRITICAL)}")
    print(f"  HIGH: {report.count_by_severity(Severity.HIGH)}")
    print(f"  MEDIUM: {report.count_by_severity(Severity.MEDIUM)}")
    print(f"  LOW: {report.count_by_severity(Severity.LOW)}")
    print("=" * 80)

    if not report.smells:
        print("\n[OK] No test smells detected!")
        return

    by_file = report.group_by_file()

    for file_path in sorted(by_file.keys()):
        smells = by_file[file_path]
        # Count by severity for this file
        critical = sum(1 for s in smells if s.severity == Severity.CRITICAL)
        high = sum(1 for s in smells if s.severity == Severity.HIGH)
        medium = sum(1 for s in smells if s.severity == Severity.MEDIUM)
        low = sum(1 for s in smells if s.severity == Severity.LOW)

        severity_summary = []
        if critical:
            severity_summary.append(f"{critical} CRITICAL")
        if high:
            severity_summary.append(f"{high} HIGH")
        if medium:
            severity_summary.append(f"{medium} MEDIUM")
        if low:
            severity_summary.append(f"{low} LOW")

        print(f"\n{file_path.name} ({', '.join(severity_summary)})")
        print("-" * 80)

        display_limit = None if verbose else 10
        for smell in smells[:display_limit]:
            print(f"  [{smell.severity.value}] Line {smell.line}: {smell.category}")
            print(f"    {smell.description}")
            if smell.snippet and verbose:
                print(f"    > {smell.snippet}")

        if not verbose and len(smells) > 10:
            print(f"  ... and {len(smells) - 10} more (use --verbose to see all)")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def parse_args(args: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze test files for code smells and anti-patterns"
    )
    parser.add_argument(
        "test_dir",
        type=Path,
        nargs="?",
        default=Path("tests"),
        help="Directory containing test files (default: tests)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show all occurrences and code snippets",
    )

    # Output format options (mutually exclusive)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON",
    )
    output_group.add_argument(
        "--sarif",
        action="store_true",
        help="Output report in SARIF format (IDE integration)",
    )
    output_group.add_argument(
        "--by-file",
        action="store_true",
        help="Group output by file (for fixing workflow)",
    )

    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Exit with non-zero code if critical smells found",
    )
    parser.add_argument(
        "--fail-on-high",
        action="store_true",
        help="Exit with non-zero code if high or critical smells found",
    )
    parser.add_argument(
        "--filter-severity",
        type=str,
        default=None,
        help="Filter output by severity (e.g., 'critical,high' or 'medium+')",
    )
    parser.add_argument(
        "--exclude-pattern",
        type=str,
        action="append",
        default=[],
        help="Exclude files matching pattern (can be repeated)",
    )
    parser.add_argument(
        "--respect-waivers",
        action="store_true",
        help="Skip issues that have inline suppressions (# noqa, # pylint: disable)",
    )

    return parser.parse_args(args)


def main(args: Sequence[str] | None = None) -> int:
    """Main entry point.

    Args:
        args: Command line arguments (None uses sys.argv)

    Returns:
        Exit code: 0 success, 1 smells found, 2 configuration error
    """
    parsed = parse_args(args)

    if not parsed.test_dir.is_dir():
        print(f"[ERROR] Directory not found: {parsed.test_dir}", file=sys.stderr)
        return 2

    # Build exclusion patterns
    exclude_patterns: list[str] = parsed.exclude_pattern or []

    report = analyze_directory(
        parsed.test_dir,
        exclude_patterns=exclude_patterns,
        respect_waivers=parsed.respect_waivers,
    )

    # Apply severity filter if specified
    if parsed.filter_severity:
        report.filter_by_severity(parsed.filter_severity)

    # Output format selection
    if parsed.json:
        print_json_report(report)
    elif parsed.sarif:
        print_sarif_report(report)
    elif parsed.by_file:
        print_by_file_report(report, verbose=parsed.verbose)
    else:
        print_report(report, verbose=parsed.verbose)

    # Exit code determination
    if parsed.fail_on_critical and report.count_by_severity(Severity.CRITICAL) > 0:
        return 1

    if parsed.fail_on_high and (
        report.count_by_severity(Severity.CRITICAL) > 0
        or report.count_by_severity(Severity.HIGH) > 0
    ):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
