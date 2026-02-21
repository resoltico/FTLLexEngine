"""FTL Linter Example - Demonstrating AST Parser Tooling API.

PARSER-ONLY: This example works WITHOUT Babel. Install with:
    pip install ftllexengine  (no [babel] extra needed)

This example shows how to use FTLLexEngine's AST parser API to build
a simple FTL linter that detects common issues:

- Messages without values
- Duplicate message IDs
- Unknown function calls
- Undefined message/term references

Note: FTL variables ($var) are provided at runtime via format_pattern() args,
not declared in FTL source, so variable validation must be runtime-based.

Leverages Python 3.13+ features:
- Pattern matching for AST node type checking
- TypeIs for type-safe visitor pattern
- Frozen dataclasses for lint rule results

Python 3.13+.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ftllexengine import parse_ftl
from ftllexengine.syntax.ast import (
    FunctionReference,
    Message,
    MessageReference,
    Resource,
    TermReference,
    VariableReference,
)
from ftllexengine.syntax.visitor import ASTVisitor


@dataclass(frozen=True, slots=True)
class LintIssue:
    """Immutable lint issue result."""

    severity: str  # "error", "warning", "info"
    rule: str  # Rule ID
    message: str  # Human-readable message
    location: str  # "message_id" or "message_id.attribute"


class FTLLinterVisitor(ASTVisitor):
    """Visitor that detects FTL lint issues using Python 3.13 pattern matching."""

    def __init__(self) -> None:
        """Initialize linter state."""
        super().__init__()
        self.issues: list[LintIssue] = []
        self.message_ids: set[str] = set()
        self.current_message_id: str | None = None

    def visit_Resource(self, node: Resource) -> None:  # pylint: disable=invalid-name
        """Visit resource and check for duplicate message IDs.

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        """
        # First pass: collect all message IDs
        for entry in node.entries:
            match entry:
                case Message(id=id_node):
                    if id_node.name in self.message_ids:
                        self.issues.append(
                            LintIssue(
                                severity="error",
                                rule="duplicate-id",
                                message=f"Duplicate message ID: {id_node.name}",
                                location=id_node.name,
                            )
                        )
                    self.message_ids.add(id_node.name)

        # Second pass: visit each message
        for entry in node.entries:
            self.visit(entry)

    def visit_Message(self, node: Message) -> None:  # pylint: disable=invalid-name
        """Visit message and check for issues.

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        """
        self.current_message_id = node.id.name

        # Check if message has a value
        if not node.value:
            self.issues.append(
                LintIssue(
                    severity="warning",
                    rule="no-value",
                    message=f"Message '{node.id.name}' has no value",
                    location=node.id.name,
                )
            )

        # Visit pattern to check references and functions
        if node.value:
            self.visit(node.value)

        # Visit attributes
        for attr in node.attributes:
            self.visit(attr)

        self.current_message_id = None

    def visit_VariableReference(self, node: VariableReference) -> None:  # pylint: disable=invalid-name
        """Visit variable reference (no validation needed - runtime provided).

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        """
        # Variables are provided at runtime, not declared in FTL
        self.generic_visit(node)

    def visit_FunctionReference(self, node: FunctionReference) -> None:  # pylint: disable=invalid-name
        """Check function calls.

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        """
        # List of known FTL functions
        # Note: For a complete linter, also check custom function registries:
        #   from ftllexengine.runtime.functions import create_default_registry
        #   registry = create_default_registry()
        #   if registry.has_function(node.id.name):
        #       return  # Custom function exists
        known_functions = {"NUMBER", "DATETIME", "CURRENCY"}

        if node.id.name not in known_functions:
            self.issues.append(
                LintIssue(
                    severity="warning",
                    rule="unknown-function",
                    message=f"Unknown function: {node.id.name}",
                    location=self.current_message_id or "unknown",
                )
            )

        self.generic_visit(node)

    def visit_MessageReference(self, node: MessageReference) -> None:  # pylint: disable=invalid-name
        """Check message references.

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        """
        if node.id.name not in self.message_ids:
            self.issues.append(
                LintIssue(
                    severity="error",
                    rule="undefined-reference",
                    message=f"Reference to undefined message: {node.id.name}",
                    location=self.current_message_id or "unknown",
                )
            )

        self.generic_visit(node)

    def visit_TermReference(self, node: TermReference) -> None:  # pylint: disable=invalid-name
        """Check term references (not implemented in this example).

        Visitor pattern: visit_* methods follow stdlib ast.NodeVisitor convention.
        """
        # In a real linter, you'd track terms too
        self.generic_visit(node)


def lint_ftl_file(source: str) -> list[LintIssue]:  # pylint: disable=redefined-outer-name
    """Lint FTL source code.

    Args:
        source: FTL source code

    Returns:
        List of lint issues found
    """
    resource = parse_ftl(source)
    linter = FTLLinterVisitor()
    linter.visit(resource)
    return linter.issues


def print_lint_results(lint_issues: list[LintIssue]) -> None:  # pylint: disable=redefined-outer-name
    """Print lint results in a readable format."""
    if not lint_issues:
        print("[OK] No issues found")
        return

    # Group by severity
    errors = [issue for issue in lint_issues if issue.severity == "error"]
    warnings = [issue for issue in lint_issues if issue.severity == "warning"]
    info = [issue for issue in lint_issues if issue.severity == "info"]

    if errors:
        print(f"\n[ERROR] {len(errors)} error(s):")
        for issue in errors:
            print(f"  [{issue.rule}] {issue.message} ({issue.location})")

    if warnings:
        print(f"\n[WARN] {len(warnings)} warning(s):")
        for issue in warnings:
            print(f"  [{issue.rule}] {issue.message} ({issue.location})")

    if info:
        print(f"\n[INFO] {len(info)} info:")
        for issue in info:
            print(f"  [{issue.rule}] {issue.message} ({issue.location})")


# Example usage
if __name__ == "__main__":
    # Example 1: Clean FTL
    print("=" * 60)
    print("Example 1: Clean FTL")
    print("=" * 60)

    # pylint: disable=invalid-name  # Example data strings - not module constants
    clean_ftl = """
hello = Hello, { $name }!
goodbye = Goodbye!
"""

    issues = lint_ftl_file(clean_ftl)
    print_lint_results(issues)

    # Example 2: Duplicate message IDs
    print("\n" + "=" * 60)
    print("Example 2: Duplicate Message IDs")
    print("=" * 60)

    duplicate_ids_ftl = """
welcome = Welcome!
welcome = Hello!
"""

    issues = lint_ftl_file(duplicate_ids_ftl)
    print_lint_results(issues)

    # Example 3: Unknown function
    print("\n" + "=" * 60)
    print("Example 3: Unknown Function")
    print("=" * 60)

    unknown_function_ftl = """
price = { PERCENTAGE($amount) }
"""

    issues = lint_ftl_file(unknown_function_ftl)
    print_lint_results(issues)

    # Example 4: Undefined message reference
    print("\n" + "=" * 60)
    print("Example 4: Undefined Message Reference")
    print("=" * 60)

    undefined_ref_ftl = """
about = About { brand-name }
"""

    issues = lint_ftl_file(undefined_ref_ftl)
    print_lint_results(issues)

    # Example 5: Message without value
    print("\n" + "=" * 60)
    print("Example 5: Message Without Value")
    print("=" * 60)

    no_value_ftl = """
# Message with only attributes (no value)
button-save =
    .tooltip = Save your work
"""

    issues = lint_ftl_file(no_value_ftl)
    print_lint_results(issues)

    # Example 6: Lint a real file
    print("\n" + "=" * 60)
    print("Example 6: Lint Real File (if exists)")
    print("=" * 60)

    ftl_file = Path("locales/en/messages.ftl")
    if ftl_file.exists():
        ftl_source = ftl_file.read_text(encoding="utf-8")
        issues = lint_ftl_file(ftl_source)
        print(f"Linting: {ftl_file}")
        print_lint_results(issues)
    else:
        print(f"File not found: {ftl_file}")

    print("\n" + "=" * 60)
    print("[SUCCESS] Linter examples complete!")
    print("=" * 60)
