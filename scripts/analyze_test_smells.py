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

Hypothesis Integration:
    - Detects non-Hypothesis tests that could benefit from property-based testing
    - Identifies tests with many parametrize cases, hardcoded example iterations,
      or multiple similar assertions that suggest a need for @given strategies
    - Detects Hypothesis anti-patterns like using .example() directly
    - Use --hypothesis-candidates for a focused report on reimagining opportunities

Exit Codes:
    0: No critical smells found
    1: Critical smells detected (with --fail-on-critical)
    2: Configuration error

Python 3.13+ required. Standard library only.
"""

import argparse
import ast
import json
import re
import sys
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeIs

# Type alias for function nodes (Python 3.12+ type statement)
type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

# Version info
__version__: Final[str] = "1.2.0"

# =============================================================================
# OUTPUT ARCHITECTURE DIRECTIVE (OAD)
# =============================================================================
# Cross-agent legibility standard for AI/human hybrid workflows.
# Format: [STATUS:8][COMPONENT:20][MESSAGE]
# Supports NO_COLOR environment variable for CI/pipeline compatibility.

# Line width for terminal output (narrow for AI agent context windows)
OAD_LINE_WIDTH: Final[int] = 72

# Fixed-width status tags (8 chars including brackets)
OAD_OK: Final[str] = "[  OK  ]"
OAD_FAIL: Final[str] = "[ FAIL ]"
OAD_INFO: Final[str] = "[ INFO ]"
OAD_WARN: Final[str] = "[ WARN ]"
OAD_CRIT: Final[str] = "[ CRIT ]"
OAD_HIGH: Final[str] = "[ HIGH ]"
OAD_MED: Final[str] = "[MEDIUM]"
OAD_LOW: Final[str] = "[ LOW  ]"

# Component width for alignment
OAD_COMPONENT_WIDTH: Final[int] = 20

# JSON block markers for easy extraction
JSON_BEGIN: Final[str] = "[SUMMARY-JSON-BEGIN]"
JSON_END: Final[str] = "[SUMMARY-JSON-END]"

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

# Patterns indicating a test could benefit from property-based testing
PROPERTY_TEST_CANDIDATE_INDICATORS: Final[frozenset[str]] = frozenset({
    # Keywords in test names suggesting multiple cases
    "various", "multiple", "different", "several", "many",
    "all", "any", "every", "combinations", "permutations",
    "edge", "corner", "boundary", "random", "fuzzy",
})

# Minimum parametrize cases to suggest Hypothesis conversion
MIN_PARAMETRIZE_CASES_FOR_HYPOTHESIS: Final[int] = 5

# Minimum hardcoded test values to suggest Hypothesis
MIN_HARDCODED_VALUES_FOR_HYPOTHESIS: Final[int] = 4

# File patterns that exempt tests from specific checks
MAGIC_VALUE_EXEMPT_PATTERNS: Final[frozenset[str]] = frozenset({
    "plural", "unicode", "cache", "diagnostic", "code", "date", "parsing",
})

# File patterns for parser/AST tests (higher assertion threshold)
PARSER_TEST_PATTERNS: Final[frozenset[str]] = frozenset({
    "parser", "ast", "syntax", "parse",
})

# Logging fixture names (exempt from broad exception checks)
LOGGING_FIXTURES: Final[frozenset[str]] = frozenset({
    "caplog", "capsys", "capfd", "logger",
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

# Suppressed variable patterns - underscore prefixed names that hide test issues
# These are variables that should typically be checked but are ignored with "_" prefix
SUPPRESSED_RESULT_PATTERNS: Final[frozenset[str]] = frozenset({
    # Common result/error suppression patterns
    "_errors", "_error", "_result", "_results", "_output", "_value", "_values",
    "_message", "_messages", "_response", "_exception", "_warnings",
    # Bundle/locale specific suppressions
    "_bundle", "_locale", "_context", "_parsed", "_formatted",
    # Generic return value suppressions
    "_ret", "_rv", "_return", "_status", "_code",
})

# Variable names that are legitimately ignored (not hiding test issues)
LEGITIMATE_IGNORED_VARIABLES: Final[frozenset[str]] = frozenset({
    "_",  # Standard throwaway variable
    "_i", "_j", "_k", "_n",  # Loop counters when only count matters
    "_unused", "_ignored",  # Explicit markers
})

# Minimum repetitions before flagging unused loop variable
MIN_LOOP_REPETITIONS_FOR_SMELL: Final[int] = 3


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
    """Load configuration from pyproject.toml if available.

    Supports the following keys in [tool.test-smells]:
        assertion-threshold: int
        assertion-threshold-parser: int
        mock-threshold: int
        min-test-name-length: int
        magic-number-threshold: int
    """
    if project_root is None:
        project_root = Path.cwd()

    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return Config()

    try:
        with pyproject.open("rb") as f:
            data = tomllib.load(f)

        config_section = data.get("tool", {}).get("test-smells", {})
        if not config_section:
            return Config()

        # Extract config values with proper None handling (0 is valid)
        def get_int(key: str, default: int) -> int:
            val = config_section.get(key)
            return val if isinstance(val, int) else default

        return Config(
            assertion_threshold=get_int("assertion-threshold", ASSERTION_OVERLOAD_THRESHOLD),
            assertion_threshold_parser=get_int("assertion-threshold-parser", 15),
            mock_threshold=get_int("mock-threshold", MOCK_OVERUSE_THRESHOLD),
            min_test_name_length=get_int("min-test-name-length", MIN_TEST_NAME_LENGTH),
            magic_number_threshold=get_int("magic-number-threshold", MAGIC_NUMBER_THRESHOLD),
        )

    except (OSError, tomllib.TOMLDecodeError):
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
class SmellReport:
    """Collection of detected smells with statistics."""

    smells: list[Smell] = field(default_factory=list)
    files_analyzed: int = 0
    tests_analyzed: int = 0

    def add(self, smell: Smell) -> None:
        """Add smell to report."""
        self.smells.append(smell)

    def sort_by_severity(self) -> None:
        """Sort smells by severity, then file, then line."""
        self.smells.sort(key=lambda s: (SEVERITY_ORDER[s.severity], str(s.file), s.line))

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
                        "level": severity_to_level[smell.severity],
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
                    },
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
                    },
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
            smells.sort(key=lambda s: (SEVERITY_ORDER[s.severity], s.line))
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
            base_order = SEVERITY_ORDER.get(Severity(base), 3)
            allowed = {s for s, order in SEVERITY_ORDER.items() if order <= base_order}
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


def is_hypothesis_decorated(node: FunctionNode) -> TypeIs[FunctionNode]:
    """Check if function has Hypothesis decorators.

    Returns TypeIs for type narrowing in callers (Python 3.13+).
    """
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


def is_skipped_test(node: FunctionNode) -> TypeIs[FunctionNode]:
    """Check if test has skip decorator (pytest.mark.skip or unittest.skip).

    Returns TypeIs for type narrowing in callers (Python 3.13+).
    """
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


def has_pytest_raises_or_warns(node: ast.AST) -> bool:
    """Check if node contains pytest.raises or pytest.warns context manager."""
    for child in ast.walk(node):
        if not isinstance(child, ast.With):
            continue
        for item in child.items:
            match item.context_expr:
                case ast.Call(func=ast.Attribute(attr="raises" | "warns")):
                    # Matches pytest.raises(Ex) or pytest.warns(Warning)
                    return True
                case ast.Call(func=ast.Name(id="raises" | "warns")):
                    # Matches directly imported raises/warns
                    return True
    return False


def has_unittest_assertion(node: ast.AST) -> bool:
    """Check if node contains unittest assertion methods.

    Detects self.assertRaises, self.assertWarns, self.assertEqual, etc.
    """
    unittest_assertions = frozenset({
        "assertEqual", "assertNotEqual", "assertTrue", "assertFalse",
        "assertIs", "assertIsNot", "assertIsNone", "assertIsNotNone",
        "assertIn", "assertNotIn", "assertIsInstance", "assertNotIsInstance",
        "assertRaises", "assertWarns", "assertLogs", "assertAlmostEqual",
        "assertNotAlmostEqual", "assertGreater", "assertGreaterEqual",
        "assertLess", "assertLessEqual", "assertRegex", "assertNotRegex",
        "assertCountEqual", "assertMultiLineEqual", "assertSequenceEqual",
        "assertListEqual", "assertTupleEqual", "assertSetEqual", "assertDictEqual",
    })
    for child in ast.walk(node):
        match child:
            case ast.Call(func=ast.Attribute(attr=attr)) if attr in unittest_assertions:
                return True
    return False


def has_caplog_fixture(node: FunctionNode) -> TypeIs[FunctionNode]:
    """Check if test function uses caplog fixture (logging tests)."""
    return any(arg.arg == "caplog" for arg in node.args.args)


def is_concurrency_test(node: FunctionNode) -> TypeIs[FunctionNode]:
    """Check if test is a concurrency/thread-safety test."""
    concurrency_keywords = {"concurrent", "thread", "parallel", "race", "deadlock"}
    name_lower = node.name.lower()
    return any(kw in name_lower for kw in concurrency_keywords)


def is_coverage_or_error_test(node: FunctionNode, file_path: Path) -> TypeIs[FunctionNode]:
    """Check if test is a coverage/error path test that may swallow exceptions."""
    # Keywords in test name that suggest legitimate exception swallowing
    name_keywords = {
        "coverage", "error", "exception", "gaps", "edge", "platform", "compat", "protocol",
    }
    # Keywords in file name that suggest comprehensive/coverage tests
    file_keywords = {"coverage", "comprehensive", "gaps", "edge"}

    name_lower = node.name.lower()
    file_lower = file_path.name.lower()

    # Check test name or file name for coverage keywords
    return any(kw in name_lower for kw in name_keywords) or any(
        kw in file_lower for kw in file_keywords
    )


def is_type_guard_conditional(node: ast.If) -> TypeIs[ast.If]:
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


def is_search_loop(loop_node: ast.For) -> TypeIs[ast.For]:
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


def is_cleanup_loop(
    loop_node: ast.For | ast.While, func_node: ast.AST,
) -> TypeIs[ast.For | ast.While]:
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
        self, file_path: Path, source: str, config: Config | None = None,
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

    def _analyze_function(self, node: FunctionNode) -> None:
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
        # Hypothesis reimagining candidates
        self._check_hypothesis_example_antipattern(node)
        self._check_non_hypothesis_candidate(node)
        # Suppression pattern detections
        self._check_suppressed_variables(node)
        self._check_unused_loop_variables(node)
        self._check_unchecked_bundle_results(node)
        # Additional quality checks
        self._check_assertions_in_except(node)
        self._check_truthiness_only_assertions(node)
        self._check_commented_assertions(node)

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
            ),
        )

    def _get_line(self, lineno: int) -> str:
        """Get source line by number (1-indexed)."""
        if 0 < lineno <= len(self.lines):
            return self.lines[lineno - 1]
        return ""

    # -------------------------------------------------------------------------
    # SMELL CHECKS
    # -------------------------------------------------------------------------

    def _check_no_assertions(self, node: FunctionNode) -> None:
        """Detect tests with no assertions."""
        # Skip tests marked with skip/xfail decorators (intentionally not implemented)
        if is_skipped_test(node):
            return

        has_assert = count_assertions(node) > 0
        has_pytest_context = has_pytest_raises_or_warns(node)
        has_unittest = has_unittest_assertion(node)

        if has_assert or has_pytest_context or has_unittest:
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

    def _check_empty_body(self, node: FunctionNode) -> None:
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

    def _check_assertion_overload(self, node: FunctionNode) -> None:
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

    def _check_weak_assertions(self, node: FunctionNode) -> None:
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

    def _check_singleton_equality(self, node: FunctionNode) -> None:
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

    def _check_broad_exceptions(self, node: FunctionNode) -> None:
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

    def _check_exception_swallowing(self, node: FunctionNode) -> None:
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
        self, node: FunctionNode,
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

    def _check_conditional_logic(self, node: FunctionNode) -> None:
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

    def _is_result_guard_conditional(self, if_node: ast.If) -> bool:
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
        self, node: FunctionNode,
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
        self, loop_node: ast.For | ast.While, func_node: FunctionNode,
    ) -> bool:
        """Check if loop appears before any assertions (setup phase)."""
        loop_lineno = loop_node.lineno

        # Check if any assertions appear before this loop
        for child in ast.walk(func_node):
            if isinstance(child, ast.Assert) and child.lineno < loop_lineno:
                return False  # There are assertions before this loop

        # No assertions before this loop - likely setup
        return True

    def _check_magic_values(self, node: FunctionNode) -> None:
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

    def _check_poor_naming(self, node: FunctionNode) -> None:
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

    def _check_io_operations(self, node: FunctionNode) -> None:
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

    def _check_time_operations(self, node: FunctionNode) -> None:
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

    def _check_excessive_mocking(self, node: FunctionNode) -> None:
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

    def _check_print_statements(self, node: FunctionNode) -> None:
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
        self, node: FunctionNode,
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
        self, node: FunctionNode,
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
        self, node: FunctionNode,
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
                        attr="NamedTemporaryFile" | "TemporaryFile" | "TemporaryDirectory",
                    ),
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
        self, func_node: FunctionNode, target: ast.AST,
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
        self, node: FunctionNode,
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

    def _check_hypothesis_example_antipattern(
        self, node: FunctionNode,
    ) -> None:
        """Detect .example() anti-pattern in Hypothesis tests.

        Per Hypothesis best practices: Never use .example() in tests as it
        bypasses Hypothesis's core strength—property-based testing with
        multiple generated examples.

        Looks for patterns like:
            st.integers().example()
            strategies.text().example()
            some_strategy.example()
        """
        # Known Hypothesis strategy module/object names
        hypothesis_names = frozenset({
            "st", "strategies", "hypothesis", "strategy",
            "integers", "floats", "text", "binary", "booleans",
            "lists", "sets", "tuples", "dictionaries", "dicts",
            "from_regex", "from_type", "builds", "one_of", "sampled_from",
            "just", "none", "characters", "emails", "uuids", "datetimes",
        })

        for child in ast.walk(node):
            match child:
                case ast.Call(
                    func=ast.Attribute(value=value, attr="example"),
                    args=[],  # .example() takes no args
                ):
                    line_text = self._get_line(child.lineno)

                    # Skip if it's @example decorator usage
                    if "@example" in line_text:
                        continue

                    # Check if value looks like a Hypothesis strategy
                    is_likely_strategy = False

                    # Direct strategy name: st.integers().example()
                    match value:
                        case ast.Call(func=ast.Attribute(value=ast.Name(id=name))):
                            if name in hypothesis_names:
                                is_likely_strategy = True
                        case ast.Call(func=ast.Name(id=name)):
                            if name in hypothesis_names:
                                is_likely_strategy = True
                        case ast.Attribute(value=ast.Name(id=name)):
                            if name in hypothesis_names:
                                is_likely_strategy = True

                    # Also check if "st." or "strategies." appears in the line
                    if "st." in line_text or "strategies." in line_text:
                        is_likely_strategy = True

                    if is_likely_strategy:
                        self._add_smell(
                            category="Hypothesis Anti-Pattern",
                            severity=Severity.HIGH,
                            line=child.lineno,
                            description=(
                                "Using .example() bypasses property-based testing; "
                                "use @given decorator or helpers like minimal(), find_any()"
                            ),
                            snippet=line_text.strip()[:60],
                            rule_id="hypothesis-example-antipattern",
                        )

    def _check_non_hypothesis_candidate(
        self, node: FunctionNode,
    ) -> None:
        """Detect non-Hypothesis tests that could benefit from property-based testing.

        Identifies tests that are good candidates for reimagining as Hypothesis tests:
        1. Tests with many parametrize cases (suggests need for broader coverage)
        2. Tests with hardcoded example lists/tuples being iterated
        3. Tests with names suggesting multiple/various/edge cases
        4. Tests with many similar assertions on different values
        """
        # Skip if already using Hypothesis
        if is_hypothesis_decorated(node):
            return

        reasons: list[str] = []

        # Check 1: Test name suggests multiple cases
        name_lower = node.name.lower()
        matching_indicators = [
            ind for ind in PROPERTY_TEST_CANDIDATE_INDICATORS
            if ind in name_lower
        ]
        if matching_indicators:
            reasons.append(f"name suggests multiple cases ({', '.join(matching_indicators)})")

        # Check 2: Parametrize decorator with many cases
        parametrize_cases = self._count_parametrize_cases(node)
        if parametrize_cases >= MIN_PARAMETRIZE_CASES_FOR_HYPOTHESIS:
            reasons.append(f"has {parametrize_cases} parametrize cases")

        # Check 3: Hardcoded example list/tuple being iterated
        hardcoded_examples = self._find_hardcoded_example_iterations(node)
        if hardcoded_examples >= MIN_HARDCODED_VALUES_FOR_HYPOTHESIS:
            reasons.append(f"iterates over {hardcoded_examples}+ hardcoded examples")

        # Check 4: Multiple similar assertions with string/number constants
        similar_assertions = self._count_similar_constant_assertions(node)
        if similar_assertions >= MIN_HARDCODED_VALUES_FOR_HYPOTHESIS:
            reasons.append(f"has {similar_assertions} similar assertions with constants")

        # Report if any reasons found
        if reasons:
            self._add_smell(
                category="Non-Hypothesis Test Candidate",
                severity=Severity.LOW,
                line=node.lineno,
                description=(
                    f"Test '{node.name}' could benefit from property-based testing: "
                    f"{'; '.join(reasons)}"
                ),
                rule_id="non-hypothesis-candidate",
            )

    def _count_parametrize_cases(
        self, node: FunctionNode,
    ) -> int:
        """Count the number of cases in pytest.mark.parametrize decorators.

        Handles:
            @pytest.mark.parametrize("x", [1, 2, 3])
            @pytest.mark.parametrize("x,y", [(1,2), (3,4)])
            @mark.parametrize("x", values)  # variable - can't count
        """
        total_cases = 0
        for decorator in node.decorator_list:
            match decorator:
                case ast.Call(func=ast.Attribute(attr="parametrize"), args=args) if len(args) >= 2:
                    # Second argument is the test cases (first is parameter names)
                    match args[1]:
                        case ast.List(elts=elts) | ast.Tuple(elts=elts):
                            total_cases += len(elts)
        return total_cases

    def _find_hardcoded_example_iterations(
        self, node: FunctionNode,
    ) -> int:
        """Find hardcoded lists/tuples being iterated in for loops."""
        max_examples = 0
        for child in walk_without_nested_definitions(node):
            match child:
                case ast.For(iter=ast.List(elts=elts) | ast.Tuple(elts=elts)):
                    # for x in [1, 2, 3, 4, 5]: - hardcoded iteration
                    max_examples = max(max_examples, len(elts))
                case ast.For(iter=ast.Name()):
                    # Check if the iterable is defined as a literal in the function
                    var_name = child.iter.id if isinstance(child.iter, ast.Name) else None
                    if var_name:
                        for stmt in node.body:
                            match stmt:
                                case ast.Assign(
                                    targets=[ast.Name(id=name)],
                                    value=ast.List(elts=elts) | ast.Tuple(elts=elts),
                                ) if name == var_name:
                                    max_examples = max(max_examples, len(elts))
        return max_examples

    def _count_similar_constant_assertions(
        self, node: FunctionNode,
    ) -> int:
        """Count assertions that compare against constant values.

        Pattern: multiple assert func(x) == "value" or assert func(x) == 123
        """
        constant_assertions = 0
        for child in ast.walk(node):
            match child:
                case ast.Assert(
                    test=ast.Compare(
                        left=ast.Call(),  # Function call on left
                        ops=[ast.Eq()],
                        comparators=[ast.Constant()],  # Constant on right
                    ),
                ):
                    constant_assertions += 1
                case ast.Assert(
                    test=ast.Compare(
                        left=ast.Constant(),  # Constant on left
                        ops=[ast.Eq()],
                        comparators=[ast.Call()],  # Function call on right
                    ),
                ):
                    constant_assertions += 1
        return constant_assertions

    def _check_suppressed_variables(self, node: FunctionNode) -> None:
        """Detect underscore-prefixed variables that suppress important results.

        Patterns like `result, _errors = bundle.format_value(...)` where
        the underscore-prefixed variable should typically be checked but is ignored.

        This is a code smell because:
        1. If success is expected, the test should verify `not _errors`
        2. If errors are expected, the test should verify error content
        3. The underscore suggests "I don't care" but tests should care

        Exemptions:
        - Standard `_` throwaway variable (legitimate for truly unneeded values)
        - Loop counters like `_i`, `_j` when only iteration count matters
        - Variables explicitly named `_unused` or `_ignored`
        """
        for child in ast.walk(node):
            match child:
                # Tuple unpacking: value, _errors = func()
                case ast.Assign(
                    targets=[ast.Tuple(elts=elements)],
                ) if len(elements) >= 2:
                    for element in elements:
                        if isinstance(element, ast.Name):
                            var_name = element.id
                            # Check if it's a suppression pattern
                            if (
                                var_name.startswith("_")
                                and var_name not in LEGITIMATE_IGNORED_VARIABLES
                            ):
                                # Check against known suppression patterns
                                if var_name in SUPPRESSED_RESULT_PATTERNS:
                                    line_text = self._get_line(child.lineno)
                                    self._add_smell(
                                        category="Suppressed Variable",
                                        severity=Severity.HIGH,
                                        line=child.lineno,
                                        description=(
                                            f"Variable '{var_name}' suppresses important result; "
                                            "should verify content or use explicit assertion"
                                        ),
                                        snippet=line_text.strip()[:70],
                                        rule_id="suppressed-variable",
                                    )
                                # Check for any underscore-prefixed name that looks like a result
                                elif var_name.startswith("_") and len(var_name) > 1:
                                    # Pattern: _<something_that_looks_important>
                                    important_suffixes = {
                                        "error", "result", "value", "output", "response",
                                        "message", "locale", "bundle", "parsed", "formatted",
                                        "warning", "exception", "status", "code",
                                    }
                                    suffix = var_name[1:].lower()
                                    if any(s in suffix for s in important_suffixes):
                                        line_text = self._get_line(child.lineno)
                                        self._add_smell(
                                            category="Suppressed Variable",
                                            severity=Severity.MEDIUM,
                                            line=child.lineno,
                                            description=(
                                                f"Variable '{var_name}' may suppress important "
                                                "result; consider explicit verification"
                                            ),
                                            snippet=line_text.strip()[:70],
                                            rule_id="suppressed-variable-possible",
                                        )

    def _check_unused_loop_variables(self, node: FunctionNode) -> None:
        """Detect loops where the loop variable is unused (repetitive test smell).

        Patterns like:
            for _ in range(10):
                assert func() == expected  # Same assertion 10 times

        This is a smell because:
        1. Repeating the same assertion doesn't increase test coverage
        2. If testing multiple cases, the loop variable should be used
        3. Suggests copy-paste testing or misunderstanding of test purpose

        Exemptions:
        - Concurrency/stress tests (multiple threads, timing tests)
        - Explicitly marked performance/benchmark tests
        - Loops that use the iteration count for setup (not repeated assertions)
        """
        # Skip performance/stress/benchmark tests
        name_lower = node.name.lower()
        exempt_keywords = (
            "performance", "stress", "benchmark", "concurrent", "thread",
            "parallel", "race", "stability", "load",
        )
        if any(kw in name_lower for kw in exempt_keywords):
            return

        for child in walk_without_nested_definitions(node):
            if not isinstance(child, ast.For):
                continue

            # Check if loop variable is underscore (unused)
            target = child.target
            if not isinstance(target, ast.Name):
                continue

            if target.id != "_":
                continue  # Loop variable is used

            # Check if iterating over range()
            match child.iter:
                case ast.Call(func=ast.Name(id="range"), args=args) if args:
                    # Get the range count
                    count_arg = args[-1] if len(args) >= 1 else None
                    if isinstance(count_arg, ast.Constant) and isinstance(
                        count_arg.value, int,
                    ):
                        iterations = count_arg.value
                        if iterations >= MIN_LOOP_REPETITIONS_FOR_SMELL:
                            # Check if loop body has assertions
                            has_assertions = any(
                                isinstance(stmt, ast.Assert)
                                for stmt in ast.walk(child)
                            )
                            if has_assertions:
                                line_text = self._get_line(child.lineno)
                                self._add_smell(
                                    category="Unused Loop Variable",
                                    severity=Severity.MEDIUM,
                                    line=child.lineno,
                                    description=(
                                        f"Loop repeats same assertion {iterations} times "
                                        "without variation; use parametrize or vary input"
                                    ),
                                    snippet=line_text.strip()[:70],
                                    rule_id="unused-loop-variable",
                                )

    def _is_variable_verified(self, node: FunctionNode, var_name: str) -> bool:
        """Check if a variable is verified anywhere in the function.

        Looks for:
        - Assert statements that reference the variable
        - If statements that check the variable
        - For loops that iterate over the variable
        """
        for child in ast.walk(node):
            is_verified = False
            match child:
                # Direct assertion on variable or negation
                case ast.Assert(test=ast.Name(id=name)) if name == var_name:
                    is_verified = True
                case ast.Assert(
                    test=ast.UnaryOp(op=ast.Not(), operand=ast.Name(id=name)),
                ) if name == var_name:
                    is_verified = True
                # Comparison or length check assertion
                case ast.Assert(
                    test=ast.Compare(left=ast.Name(id=name)),
                ) if name == var_name:
                    is_verified = True
                case ast.Assert(
                    test=ast.Compare(
                        left=ast.Call(func=ast.Name(id="len"), args=[ast.Name(id=name)]),
                    ),
                ) if name == var_name:
                    is_verified = True
                # Conditional checks or iteration
                case ast.If(test=ast.Name(id=name)) if name == var_name:
                    is_verified = True
                case ast.If(
                    test=ast.UnaryOp(op=ast.Not(), operand=ast.Name(id=name)),
                ) if name == var_name:
                    is_verified = True
                case ast.For(iter=ast.Name(id=name)) if name == var_name:
                    is_verified = True
            if is_verified:
                return True
        return False

    def _check_unchecked_bundle_results(self, node: FunctionNode) -> None:
        """Detect bundle.format_* calls where results are not verified.

        Patterns like:
            result, errors = bundle.format_value("msg")
            assert isinstance(result, str)  # Only checks type, not content
            # errors is never checked!

        This is a smell because:
        1. Bundle operations return (result, errors) tuple
        2. Tests should verify BOTH the result content AND error state
        3. Just checking type or non-None doesn't verify correct behavior

        This specifically targets FTL bundle testing patterns to ensure
        individual message/bundle behavior is properly verified.
        """
        # Track format_* calls and what gets checked
        format_calls: list[tuple[int, str, list[str]]] = []  # (line, method, var_names)

        for child in ast.walk(node):
            match child:
                # Pattern: tuple unpacking from format_value or format_pattern
                case ast.Assign(
                    targets=[ast.Tuple(elts=[result_var, errors_var])],
                    value=ast.Call(
                        func=ast.Attribute(
                            attr="format_value" | "format_pattern" as method,
                        ),
                    ),
                ):
                    result_name = (
                        result_var.id if isinstance(result_var, ast.Name) else None
                    )
                    errors_name = (
                        errors_var.id if isinstance(errors_var, ast.Name) else None
                    )
                    if result_name and errors_name:
                        format_calls.append(
                            (child.lineno, method, [result_name, errors_name]),
                        )

        # For each format call, check if errors are properly verified
        for line, method, var_names in format_calls:
            _result_name, errors_name = var_names

            # Skip if errors var is underscore-prefixed (already caught by other check)
            if errors_name.startswith("_"):
                continue

            if not self._is_variable_verified(node, errors_name):
                line_text = self._get_line(line)
                self._add_smell(
                    category="Unchecked Bundle Result",
                    severity=Severity.MEDIUM,
                    line=line,
                    description=(
                        f"bundle.{method}() errors not verified; "
                        f"'{errors_name}' should be checked"
                    ),
                    snippet=line_text.strip()[:70],
                    rule_id="unchecked-bundle-result",
                )

    def _check_assertions_in_except(self, node: FunctionNode) -> None:
        """Detect assertions inside except blocks (hidden test failures).

        Patterns like:
            try:
                risky_operation()
            except SomeException:
                assert False, "Should not raise"  # This hides the actual exception

        This is a smell because:
        1. The actual exception details are lost
        2. Use pytest.raises() or pytest.fail() with proper context instead
        3. May mask unexpected exceptions

        Exemptions:
        - Re-raise after assertion
        - Logging before assertion
        - Hypothesis tests (may legitimately catch and check exceptions)
        """
        if is_hypothesis_decorated(node):
            return

        for child in ast.walk(node):
            if not isinstance(child, ast.ExceptHandler):
                continue

            # Check if except block contains assertions
            for stmt in child.body:
                if isinstance(stmt, ast.Assert):
                    # Check if it's assert False (explicit failure)
                    match stmt.test:
                        case ast.Constant(value=False):
                            self._add_smell(
                                category="Assertion in Except Block",
                                severity=Severity.MEDIUM,
                                line=stmt.lineno,
                                description=(
                                    "assert False in except block; "
                                    "use pytest.raises() for expected exceptions"
                                ),
                                rule_id="assert-in-except",
                            )

    def _check_truthiness_only_assertions(self, node: FunctionNode) -> None:
        """Detect assertions that only check truthiness without specific comparison.

        Patterns like:
            result = func()
            assert result  # Only checks truthiness, not specific value

        This is a smell because:
        1. Empty string, empty list, 0 would all fail unexpectedly
        2. Non-empty wrong value would pass unexpectedly
        3. Should use specific comparisons: assert result == expected

        Exemptions:
        - assert not x (checking falsiness is more specific)
        - assert x is not None (explicit None check)
        - Boolean return values (when function name suggests boolean)
        - Error checking patterns (assert errors, assert not errors)
        """
        # Track variable names that are likely booleans or errors
        boolean_like_names = {
            "is_", "has_", "can_", "should_", "was_", "valid", "success",
            "found", "exists", "enabled", "disabled", "empty", "errors",
        }

        for child in ast.walk(node):
            if not isinstance(child, ast.Assert):
                continue

            match child.test:
                # assert result (just a name, not a comparison)
                case ast.Name(id=name):
                    # Skip if name suggests boolean semantics
                    if any(bp in name.lower() for bp in boolean_like_names):
                        continue
                    # Skip common result guard names
                    if name in {"errors", "warnings", "result", "results"}:
                        continue

                    line_text = self._get_line(child.lineno)
                    self._add_smell(
                        category="Truthiness-Only Assertion",
                        severity=Severity.LOW,
                        line=child.lineno,
                        description=(
                            f"assert {name} only checks truthiness; "
                            "consider specific comparison"
                        ),
                        snippet=line_text.strip()[:70],
                        rule_id="truthiness-only-assert",
                    )

    def _check_commented_assertions(self, node: FunctionNode) -> None:
        """Detect commented-out assertions that may indicate disabled tests.

        Patterns like:
            # assert result == expected  # TODO: fix later
            # self.assertEqual(a, b)

        This is a smell because:
        1. Commented code suggests unfinished or broken tests
        2. Should either fix the assertion or remove it entirely
        3. May leave test without proper verification
        """
        # Check source lines within the function
        if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
            return

        start_line = node.lineno
        end_line = node.end_lineno or start_line

        for lineno in range(start_line, end_line + 1):
            line = self._get_line(lineno).strip()
            if not line.startswith("#"):
                continue

            # Check for commented assertion patterns
            comment_content = line[1:].strip()
            assertion_patterns = (
                "assert ", "self.assert", "assertEqual", "assertTrue",
                "assertFalse", "assertRaises", "pytest.raises",
            )
            if any(comment_content.startswith(p) for p in assertion_patterns):
                self._add_smell(
                    category="Commented Assertion",
                    severity=Severity.MEDIUM,
                    line=lineno,
                    description="Commented-out assertion; fix or remove",
                    snippet=line[:60],
                    rule_id="commented-assertion",
                )


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
    """Recursively discover test files in directory.

    Discovers:
        - test_*.py files
        - *_test.py files
        - conftest.py files

    Excludes hidden directories (.) and __pycache__.
    """
    # Use rglob for efficient recursive discovery
    for pattern in ("test_*.py", "*_test.py", "conftest.py"):
        for path in test_dir.rglob(pattern):
            # Skip hidden directories and __pycache__
            if not any(part.startswith((".", "__")) for part in path.parts):
                yield path


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
            test_file, config, respect_waivers=respect_waivers,
        )
        report.tests_analyzed += test_count
        for smell in smells:
            report.add(smell)

    report.sort_by_severity()
    return report


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================


def _oad_line(status: str, component: str, message: str) -> str:
    """Format a line in OAD (Output Architecture Directive) format.

    Format: [STATUS:8][COMPONENT:20][MESSAGE]
    Example: [  OK  ] Files Analyzed     : 201
    """
    comp_padded = f"{component:<{OAD_COMPONENT_WIDTH}}"
    return f"{status} {comp_padded}: {message}"


def _severity_to_oad(severity: Severity) -> str:
    """Map severity to OAD status tag."""
    return {
        Severity.CRITICAL: OAD_CRIT,
        Severity.HIGH: OAD_HIGH,
        Severity.MEDIUM: OAD_MED,
        Severity.LOW: OAD_LOW,
    }[severity]


def print_oad_report(report: SmellReport, *, verbose: bool = False) -> None:
    """Print smell report in OAD format for AI agent consumption.

    OAD (Output Architecture Directive) provides:
    - Fixed-width status tags for reliable parsing
    - Consistent alignment for visual scanning
    - JSON summary block with extraction markers
    - Narrow width (72 chars) for context window efficiency
    """
    w = OAD_LINE_WIDTH
    print("=" * w)
    print("TEST SMELL ANALYSIS REPORT (OAD FORMAT)")
    print("=" * w)

    # Summary section with fixed-width formatting
    crit = report.count_by_severity(Severity.CRITICAL)
    high = report.count_by_severity(Severity.HIGH)
    med = report.count_by_severity(Severity.MEDIUM)
    low = report.count_by_severity(Severity.LOW)

    status = OAD_OK if crit == 0 and high == 0 else OAD_FAIL
    print(_oad_line(status, "Analysis Status", "PASS" if status == OAD_OK else "FAIL"))
    print(_oad_line(OAD_INFO, "Files Analyzed", str(report.files_analyzed)))
    print(_oad_line(OAD_INFO, "Tests Analyzed", str(report.tests_analyzed)))
    print(_oad_line(OAD_INFO, "Total Smells", str(len(report.smells))))

    # Severity breakdown
    print("-" * w)
    if crit > 0:
        print(_oad_line(OAD_CRIT, "Critical", str(crit)))
    if high > 0:
        print(_oad_line(OAD_HIGH, "High", str(high)))
    if med > 0:
        print(_oad_line(OAD_MED, "Medium", str(med)))
    if low > 0:
        print(_oad_line(OAD_LOW, "Low", str(low)))
    print("=" * w)

    if not report.smells:
        print(_oad_line(OAD_OK, "Result", "No test smells detected"))
        return

    # Group by category
    by_category: dict[str, list[Smell]] = {}
    for smell in report.smells:
        by_category.setdefault(smell.category, []).append(smell)

    # Print each category
    for category in sorted(by_category.keys()):
        smells = by_category[category]
        print()
        print(f"[CATEGORY] {category} ({len(smells)})")
        print("-" * w)

        display_limit = None if verbose else 5
        for smell in smells[:display_limit]:
            tag = _severity_to_oad(smell.severity)
            loc = f"{smell.file.name}:{smell.line}"
            # Truncate description to fit width
            max_desc = w - 10 - len(loc) - 3
            desc = smell.description[:max_desc]
            if len(smell.description) > max_desc:
                desc = desc[: max_desc - 3] + "..."
            print(f"{tag} {loc}")
            print(f"         {desc}")

        remaining = len(smells) - (display_limit or len(smells))
        if remaining > 0:
            print(f"         ... +{remaining} more (use --verbose)")

    # JSON summary block for programmatic extraction
    print()
    print("=" * w)
    print(JSON_BEGIN)
    summary = {
        "status": "pass" if crit == 0 and high == 0 else "fail",
        "files": report.files_analyzed,
        "tests": report.tests_analyzed,
        "total": len(report.smells),
        "critical": crit,
        "high": high,
        "medium": med,
        "low": low,
    }
    print(json.dumps(summary, separators=(",", ":")))
    print(JSON_END)


def print_report(report: SmellReport, *, verbose: bool = False) -> None:
    """Print smell report to stdout (human-readable format)."""
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


def print_json_report(report: SmellReport, *, compact: bool = False) -> None:
    """Print smell report as JSON with extraction markers.

    Args:
        report: The smell report to print.
        compact: If True, output single-line JSON (for piping).

    """
    print(JSON_BEGIN)
    if compact:
        print(json.dumps(report.to_dict(), separators=(",", ":")))
    else:
        print(json.dumps(report.to_dict(), indent=2))
    print(JSON_END)


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


def print_hypothesis_candidates_report(report: SmellReport, *, verbose: bool = False) -> None:
    """Print report focused on non-Hypothesis test candidates and anti-patterns.

    This report helps identify tests that could benefit from property-based testing
    and highlights Hypothesis anti-patterns (like .example() usage).
    """
    # Filter to only Hypothesis-related smells
    hypothesis_categories = {
        "Non-Hypothesis Test Candidate",
        "Hypothesis Anti-Pattern",
    }
    candidates = [s for s in report.smells if s.category in hypothesis_categories]

    print("=" * 80)
    print("HYPOTHESIS REIMAGINING CANDIDATES REPORT")
    print("=" * 80)
    print(f"Files analyzed: {report.files_analyzed}")
    print(f"Tests analyzed: {report.tests_analyzed}")
    print("=" * 80)

    if not candidates:
        print("\n[OK] No tests identified as Hypothesis candidates or anti-patterns!")
        print("\nTip: All your tests either already use Hypothesis or don't show")
        print("     patterns that would benefit from property-based testing.")
        return

    # Separate anti-patterns from candidates
    anti_patterns = [s for s in candidates if s.category == "Hypothesis Anti-Pattern"]
    reimagine_candidates = [s for s in candidates if s.category == "Non-Hypothesis Test Candidate"]

    # Print anti-patterns first (higher priority)
    if anti_patterns:
        print(f"\n[!] HYPOTHESIS ANTI-PATTERNS ({len(anti_patterns)} found)")
        print("-" * 80)
        print("These tests misuse Hypothesis features and should be fixed:")
        print()
        for smell in anti_patterns:
            print(f"  {smell.file.name}:{smell.line}")
            print(f"    {smell.description}")
            if smell.snippet and verbose:
                print(f"    > {smell.snippet}")
        print()
        print("FIX: Replace .example() calls with @given decorator or use helper")
        print("     functions from tests.common.debug: minimal(), find_any(),")
        print("     assert_all_examples(), assert_simple_property()")

    # Print candidates
    if reimagine_candidates:
        print(f"\n[*] TESTS TO REIMAGINE AS PROPERTY-BASED ({len(reimagine_candidates)} found)")
        print("-" * 80)
        print("These tests could benefit from Hypothesis property-based testing:")
        print()

        # Group by file
        by_file: dict[Path, list[Smell]] = {}
        for smell in reimagine_candidates:
            by_file.setdefault(smell.file, []).append(smell)

        for file_path in sorted(by_file.keys()):
            smells = by_file[file_path]
            print(f"\n  {file_path.name} ({len(smells)} candidates)")
            for smell in smells:
                # Extract just the test name from description
                desc = smell.description
                print(f"    Line {smell.line}: {desc}")

        print()
        print("-" * 80)
        print("REIMAGINING GUIDE:")
        print("-" * 80)
        print("""
How to convert these tests to property-based tests:

1. PARAMETRIZED TESTS → @given with strategies
   Before: @pytest.mark.parametrize("x", [1, 2, 3, 4, 5])
   After:  @given(x=st.integers(min_value=1, max_value=5))

2. HARDCODED EXAMPLE LOOPS → @given with strategies
   Before: for val in ["a", "b", "c", "d"]:
   After:  @given(val=st.text(min_size=1, max_size=1))

3. MULTIPLE SIMILAR ASSERTIONS → Single @given test
   Before: assert func("a") == expected_a
           assert func("b") == expected_b
   After:  @given(input=st.text())
           def test_func_properties(input):
               result = func(input)
               # Assert properties that hold for ALL inputs

4. EDGE/BOUNDARY TESTS → Use st.one_of() or assume()
   Before: test_edge_case_empty(), test_edge_case_large()
   After:  @given(st.one_of(st.just(""), st.text(min_size=1000)))

Key Hypothesis strategies:
  - st.integers(), st.floats(), st.text(), st.binary()
  - st.lists(), st.dictionaries(), st.tuples()
  - st.one_of(), st.sampled_from(), st.builds()
  - st.from_regex() for pattern-based generation

Documentation: https://hypothesis.readthedocs.io/
""")

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Anti-patterns to fix:    {len(anti_patterns)}")
    print(f"  Tests to reimagine:      {len(reimagine_candidates)}")
    print(f"  Total opportunities:     {len(candidates)}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def parse_args(args: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze test files for code smells and anti-patterns",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
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
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List all available smell detection rules and exit",
    )

    # Output format options (mutually exclusive)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--oad",
        action="store_true",
        help="OAD format: fixed-width tags, narrow output for AI agents",
    )
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON with extraction markers",
    )
    output_group.add_argument(
        "--json-compact",
        action="store_true",
        help="Output report as single-line JSON (for piping)",
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
    output_group.add_argument(
        "--hypothesis-candidates",
        action="store_true",
        help="List only tests that could be reimagined as Hypothesis property-based tests",
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


# All available detection rules with descriptions
# Format: (rule_id, severity, description) tuples
AVAILABLE_RULES: Final[tuple[tuple[str, str, str], ...]] = (
    ("tests-without-assertions", "CRITICAL", "Tests with no assertions or verification"),
    ("empty-test-body", "HIGH", "Tests with only docstring, no implementation"),
    ("assertion-overload", "MEDIUM", "Tests with too many assertions (>10)"),
    ("weak-assertions", "HIGH", "Tautological assertions like 'assert True'"),
    ("singleton-equality", "MEDIUM", "Using == None instead of 'is None'"),
    ("broad-exception-handling", "HIGH", "Bare except or catching generic Exception"),
    ("exception-swallowing", "HIGH", "Except blocks that silently swallow with 'pass'"),
    ("missing-pytest-raises", "MEDIUM", "Try/except instead of pytest.raises()"),
    ("conditional-logic", "MEDIUM", "If statements in tests make behavior unclear"),
    ("loops-in-tests", "MEDIUM", "Loops suggest multiple cases; use parametrize"),
    ("magic-values", "LOW", "Large magic numbers without explanation"),
    ("poor-test-naming", "MEDIUM", "Generic or too-short test names"),
    ("io-in-unit-tests", "MEDIUM", "File I/O in tests; use fixtures"),
    ("sleep-based-sync", "HIGH", "time.sleep() makes tests slow and flaky"),
    ("time-dependent-tests", "MEDIUM", "Calls to now()/today() should be mocked"),
    ("overuse-of-mocks", "MEDIUM", "Tests with too many mocks (>5)"),
    ("print-in-tests", "LOW", "print() in tests; use logging or capsys"),
    ("duplicate-assertions", "MEDIUM", "Same assertion appears multiple times"),
    ("flaky-random", "HIGH", "Random calls without seed; non-deterministic"),
    ("flaky-uuid", "MEDIUM", "uuid4() in assertions; generates new value each run"),
    ("incomplete-cleanup-tempfile", "MEDIUM", "tempfile without context manager"),
    ("incomplete-cleanup-chdir", "HIGH", "os.chdir() without restoring directory"),
    ("hardcoded-path", "MEDIUM", "Platform-specific paths in tests"),
    ("hypothesis-example-antipattern", "HIGH", ".example() bypasses property testing"),
    ("non-hypothesis-candidate", "LOW", "Test could benefit from Hypothesis"),
    ("suppressed-variable", "HIGH", "Underscore-prefixed var suppresses result"),
    ("unused-loop-variable", "MEDIUM", "Loop repeats same test without variation"),
    ("unchecked-bundle-result", "MEDIUM", "bundle.format_* errors not verified"),
    ("assert-in-except", "MEDIUM", "assert False in except block"),
    ("truthiness-only-assert", "LOW", "Assert only checks truthiness, not value"),
    ("commented-assertion", "MEDIUM", "Commented-out assertion in test"),
    ("bad-filename", "LOW", "Test filename follows bad naming pattern"),
)


def print_rules_list() -> None:
    """Print all available detection rules in OAD format."""
    w = OAD_LINE_WIDTH
    print("=" * w)
    print("AVAILABLE TEST SMELL DETECTION RULES")
    print("=" * w)
    print(_oad_line(OAD_INFO, "Total Rules", str(len(AVAILABLE_RULES))))
    print()

    # Group by severity
    by_severity: dict[str, list[tuple[str, str]]] = {
        "CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": [],
    }
    for rule_id, severity, desc in AVAILABLE_RULES:
        by_severity[severity].append((rule_id, desc))

    severity_tags = {
        "CRITICAL": OAD_CRIT, "HIGH": OAD_HIGH,
        "MEDIUM": OAD_MED, "LOW": OAD_LOW,
    }
    for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        rules = by_severity[severity]
        if rules:
            print(f"{severity_tags[severity]} [{severity}] ({len(rules)} rules)")
            print("-" * w)
            for rule_id, desc in rules:
                # Truncate description to fit OAD width
                desc_trunc = desc if len(desc) < w else desc[: w - 7] + "..."
                print(f"  {rule_id}")
                print(f"    {desc_trunc}")
            print()

    print("=" * w)
    print(_oad_line(OAD_INFO, "Suppress", "# test-smell: ignore[rule-id]"))
    print(_oad_line(OAD_INFO, "Filter", "--filter-severity=high+"))


def main(args: Sequence[str] | None = None) -> int:
    """Main entry point.

    Args:
        args: Command line arguments (None uses sys.argv)

    Returns:
        Exit code: 0 success, 1 smells found, 2 configuration error

    """
    parsed = parse_args(args)

    # Handle --list-rules before directory check
    if parsed.list_rules:
        print_rules_list()
        return 0

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
    if parsed.oad:
        print_oad_report(report, verbose=parsed.verbose)
    elif parsed.json:
        print_json_report(report)
    elif parsed.json_compact:
        print_json_report(report, compact=True)
    elif parsed.sarif:
        print_sarif_report(report)
    elif parsed.by_file:
        print_by_file_report(report, verbose=parsed.verbose)
    elif parsed.hypothesis_candidates:
        print_hypothesis_candidates_report(report, verbose=parsed.verbose)
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
